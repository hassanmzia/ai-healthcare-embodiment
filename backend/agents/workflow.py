"""Main pipeline orchestrator for the MS screening workflow."""
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd
from django.conf import settings
from django.utils import timezone

from .base import AgentOutput
from .retrieval import RetrievalAgent
from .phenotyping import PhenotypingAgentV2
from .notes_imaging import NotesImagingAgent
from .safety import SafetyGovernanceAgent
from .coordinator import Coordinator

logger = logging.getLogger('agents')

# ---------------------------------------------------------------------------
# Column lists used when converting ORM objects to a DataFrame
# ---------------------------------------------------------------------------

SYMPTOM_COLS = [
    'optic_neuritis',
    'paresthesia',
    'weakness',
    'gait_instability',
    'vertigo',
    'fatigue',
    'bladder_issues',
    'cognitive_fog',
]

EXTENDED_COLS = [
    'vitamin_d_deficient',
    'infectious_mono_history',
    'smartform_neuro',
    'paths_like_function',
]

BASE_COLS = [
    'patient_id',
    'age',
    'sex',
    'mri_lesions',
    'note_has_ms_terms',
    'visit_count',
    'note_text',
    'lookalike_condition',
    'ms_diagnosis',
]


def _patients_to_dataframe(patients_qs, limit: Optional[int] = None) -> pd.DataFrame:
    """Convert a Patient queryset into a pandas DataFrame."""
    cols = BASE_COLS + SYMPTOM_COLS + EXTENDED_COLS
    records = []
    qs = patients_qs.all()
    if limit:
        qs = qs[:limit]
    for p in qs:
        row = {}
        for col in cols:
            row[col] = getattr(p, col, None)
        records.append(row)
    return pd.DataFrame(records)


def _patient_row_to_dict(row: pd.Series) -> Dict[str, Any]:
    """Convert a single DataFrame row to a plain dict for agent consumption."""
    d = row.to_dict()
    # Ensure native Python types for JSON serialization
    for k, v in d.items():
        if pd.isna(v):
            d[k] = None
        elif hasattr(v, 'item'):
            d[k] = v.item()
    return d


def build_patient_card(
    patient_data: Dict[str, Any],
    phenotyping_output: AgentOutput,
    notes_output: AgentOutput,
    safety_output: AgentOutput,
    coordinator_output: AgentOutput,
) -> Dict[str, Any]:
    """
    Assemble a single patient risk card from all agent outputs.

    This card is the primary data structure persisted as a
    RiskAssessment and displayed in the frontend.
    """
    risk_score = phenotyping_output.payload.get('risk_score', 0.0)
    feature_contributions = phenotyping_output.payload.get('feature_contributions', {})

    card = {
        'patient_id': patient_data.get('patient_id', 'UNKNOWN'),
        'age': patient_data.get('age'),
        'sex': patient_data.get('sex'),
        'risk_score': risk_score,
        'model_version': phenotyping_output.payload.get('model_version', 'v2'),
        'feature_contributions': feature_contributions,
        'top_features': sorted(
            [(k, v) for k, v in feature_contributions.items() if v > 0],
            key=lambda x: x[1],
            reverse=True,
        )[:5],
        'lookalike_condition': patient_data.get('lookalike_condition', 'none'),
        'lookalike_penalty': feature_contributions.get('lookalike_penalty', 0.0),
        'note_ms_terms_flag': notes_output.payload.get('note_ms_terms_flag', False),
        'note_nonms_terms_flag': notes_output.payload.get('note_nonms_terms_flag', False),
        'note_excerpt': notes_output.payload.get('note_excerpt', ''),
        'ms_terms_found': notes_output.payload.get('ms_terms_found', []),
        'nonms_terms_found': notes_output.payload.get('nonms_terms_found', []),
        'safety_flags': safety_output.payload.get('flags', []),
        'safety_flag_count': safety_output.payload.get('flag_count', 0),
        'action': coordinator_output.payload.get('action', 'NO_ACTION'),
        'autonomy_level': coordinator_output.payload.get('autonomy_level', 0),
        'rationale': coordinator_output.payload.get('rationale', []),
        'ms_diagnosis_actual': patient_data.get('ms_diagnosis', False),
    }
    return card


def run_screening_workflow(
    policy_config_id: Optional[str] = None,
    patient_limit: Optional[int] = None,
) -> str:
    """
    Execute the full multi-agent MS screening pipeline.

    Steps
    -----
    1. Create a WorkflowRun record.
    2. Load patients from the DB into a DataFrame.
    3. Run RetrievalAgent to get candidate patient IDs.
    4. For each candidate, run the agent chain:
       PhenotypingAgentV2 -> NotesImagingAgent -> SafetyGovernanceAgent -> Coordinator
    5. Build patient cards and persist RiskAssessment records.
    6. Compute performance metrics (precision, recall, confusion counts).
    7. Update the WorkflowRun with results and metrics.

    Parameters
    ----------
    policy_config_id : str or None
        UUID string for a governance.PolicyConfig record. If None,
        system defaults from settings.MS_RISK_POLICY are used.
    patient_limit : int or None
        Maximum number of patients to load (useful for dev/testing).

    Returns
    -------
    str
        The UUID (as string) of the created WorkflowRun.
    """
    from patients.models import Patient, WorkflowRun, RiskAssessment
    from .models import AgentExecution

    workflow_start = time.time()

    # ---- Load policy ----
    policy = dict(settings.MS_RISK_POLICY)
    if policy_config_id:
        try:
            from governance.models import PolicyConfig
            pc = PolicyConfig.objects.get(pk=policy_config_id)
            policy.update({
                'risk_review_threshold': pc.risk_review_threshold,
                'draft_order_threshold': pc.draft_order_threshold,
                'auto_order_threshold': pc.auto_order_threshold,
                'max_auto_actions_per_day': pc.max_auto_actions_per_day,
            })
        except Exception as e:
            logger.warning(f"Could not load PolicyConfig {policy_config_id}: {e}")

    # ---- Create WorkflowRun ----
    wf_run = WorkflowRun.objects.create(
        status='running',
        policy_snapshot=policy,
    )
    logger.info(f"WorkflowRun {wf_run.id} started.")

    try:
        # ---- Step 2: Load patients ----
        patients_df = _patients_to_dataframe(Patient.objects, limit=patient_limit)
        if patients_df.empty:
            wf_run.status = 'completed'
            wf_run.results = {'error': 'No patients found', 'patient_cards': []}
            wf_run.save()
            return str(wf_run.id)

        # ---- Step 3: Retrieval ----
        retrieval = RetrievalAgent()
        retrieval_out = retrieval.timed_execute(patients_df)

        AgentExecution.objects.create(
            run=wf_run,
            agent_name='retrieval',
            patient_id_ref='ALL',
            payload=retrieval_out.payload,
            duration_ms=retrieval_out.duration_ms,
        )

        candidate_ids = retrieval_out.payload.get('candidate_ids', [])
        if not candidate_ids:
            wf_run.status = 'completed'
            wf_run.results = {
                'patient_cards': [],
                'retrieval': retrieval_out.payload,
                'metrics': {},
            }
            wf_run.save()
            return str(wf_run.id)

        # ---- Step 4: Per-candidate agent chain ----
        phenotyper = PhenotypingAgentV2()
        notes_agent = NotesImagingAgent()
        safety_agent = SafetyGovernanceAgent()
        coord = Coordinator(policy=policy)
        coord._reset_rate_limit()

        patient_cards: List[Dict[str, Any]] = []
        candidates_df = patients_df[patients_df['patient_id'].isin(candidate_ids)]

        for _, row in candidates_df.iterrows():
            patient_data = _patient_row_to_dict(row)
            pid = patient_data.get('patient_id', 'UNKNOWN')

            # -- Phenotyping --
            pheno_out = phenotyper.timed_execute(patient_data)
            AgentExecution.objects.create(
                run=wf_run,
                agent_name='phenotyping',
                patient_id_ref=pid,
                payload=pheno_out.payload,
                duration_ms=pheno_out.duration_ms,
            )
            risk_score = pheno_out.payload.get('risk_score', 0.0)

            # -- Notes & Imaging --
            notes_out = notes_agent.timed_execute(patient_data)
            AgentExecution.objects.create(
                run=wf_run,
                agent_name='notes_imaging',
                patient_id_ref=pid,
                payload=notes_out.payload,
                duration_ms=notes_out.duration_ms,
            )

            # -- Safety --
            safety_out = safety_agent.timed_execute(patient_data, risk_score)
            AgentExecution.objects.create(
                run=wf_run,
                agent_name='safety_governance',
                patient_id_ref=pid,
                payload=safety_out.payload,
                duration_ms=safety_out.duration_ms,
            )

            # -- Coordinator --
            coord_out = coord.timed_execute(risk_score, safety_out.payload)
            AgentExecution.objects.create(
                run=wf_run,
                agent_name='coordinator',
                patient_id_ref=pid,
                payload=coord_out.payload,
                duration_ms=coord_out.duration_ms,
            )

            # -- Build card --
            card = build_patient_card(
                patient_data, pheno_out, notes_out, safety_out, coord_out,
            )
            patient_cards.append(card)

            # -- Persist RiskAssessment --
            try:
                patient_obj = Patient.objects.get(patient_id=pid)
                RiskAssessment.objects.create(
                    patient=patient_obj,
                    workflow_run=wf_run,
                    risk_score=risk_score,
                    action=coord_out.payload.get('action', 'NO_ACTION'),
                    autonomy_level=coord_out.payload.get('autonomy_level', 0),
                    feature_contributions=pheno_out.payload.get('feature_contributions', {}),
                    safety_flags=safety_out.payload.get('flags', []),
                    card=card,
                )
            except Exception as e:
                logger.error(f"Failed to create RiskAssessment for {pid}: {e}")

        # ---- Step 6: Compute metrics ----
        metrics = _compute_metrics(patient_cards, policy)

        # ---- Step 7: Update WorkflowRun ----
        workflow_duration = (time.time() - workflow_start) * 1000
        wf_run.status = 'completed'
        wf_run.results = {
            'retrieval': retrieval_out.payload,
            'patient_cards': patient_cards,
            'metrics': metrics,
            'total_duration_ms': round(workflow_duration, 1),
            'candidates_count': len(candidate_ids),
            'total_patients': len(patients_df),
        }
        wf_run.save()

        logger.info(
            f"WorkflowRun {wf_run.id} completed in {workflow_duration:.1f}ms. "
            f"Cards: {len(patient_cards)}  Metrics: {metrics}"
        )
        return str(wf_run.id)

    except Exception as e:
        logger.exception(f"WorkflowRun {wf_run.id} failed: {e}")
        wf_run.status = 'failed'
        wf_run.results = {'error': str(e)}
        wf_run.save()
        raise


def _compute_metrics(
    patient_cards: List[Dict[str, Any]],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute precision, recall, and confusion matrix counts from
    the set of patient cards produced by the workflow.

    A patient is considered "flagged" if its action is anything other
    than NO_ACTION.  Ground truth comes from ``ms_diagnosis_actual``.
    """
    review_thresh = policy.get('risk_review_threshold', 0.65)

    tp = 0  # flagged AND has MS
    fp = 0  # flagged AND no MS
    fn = 0  # not flagged AND has MS
    tn = 0  # not flagged AND no MS

    for card in patient_cards:
        flagged = card.get('action', 'NO_ACTION') != 'NO_ACTION'
        actual_ms = bool(card.get('ms_diagnosis_actual', False))

        if flagged and actual_ms:
            tp += 1
        elif flagged and not actual_ms:
            fp += 1
        elif not flagged and actual_ms:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        'true_positives': tp,
        'false_positives': fp,
        'false_negatives': fn,
        'true_negatives': tn,
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1_score': round(f1, 4),
        'total_evaluated': len(patient_cards),
        'review_threshold_used': review_thresh,
    }

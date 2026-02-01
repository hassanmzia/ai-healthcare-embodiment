"""REST API serializers."""
from rest_framework import serializers
from patients.models import Patient, RiskAssessment, PolicyConfiguration, WorkflowRun
from governance.models import GovernanceRule, ComplianceReport
from core.models import AuditLog, Notification


class PatientListSerializer(serializers.ModelSerializer):
    symptom_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Patient
        fields = [
            'id', 'patient_id', 'age', 'sex', 'visits_last_year',
            'lookalike_dx', 'has_mri', 'mri_lesions', 'note_has_ms_terms',
            'true_at_risk', 'symptom_count', 'optic_neuritis', 'paresthesia',
            'weakness', 'gait_instability', 'vertigo', 'fatigue',
            'bladder_issues', 'cognitive_fog', 'vitamin_d_ngml',
            'vitamin_d_deficient', 'infectious_mono_history',
            'smartform_neuro_symptom_score', 'paths_like_function_score',
            'created_at',
        ]


class PatientDetailSerializer(serializers.ModelSerializer):
    symptom_count = serializers.ReadOnlyField()
    risk_assessments = serializers.SerializerMethodField()
    
    class Meta:
        model = Patient
        fields = '__all__'
    
    def get_risk_assessments(self, obj):
        assessments = obj.risk_assessments.order_by('-created_at')[:10]
        return RiskAssessmentSerializer(assessments, many=True).data


class RiskAssessmentSerializer(serializers.ModelSerializer):
    patient_display = serializers.CharField(source='patient.patient_id', read_only=True)
    
    class Meta:
        model = RiskAssessment
        fields = [
            'id', 'patient', 'patient_display', 'run_id', 'risk_score',
            'action', 'autonomy_level', 'feature_contributions', 'flags',
            'flag_count', 'rationale', 'notes_analysis', 'llm_summary',
            'patient_card', 'reviewed_by', 'review_notes', 'reviewed_at',
            'created_at',
        ]


class PolicyConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyConfiguration
        fields = '__all__'


class WorkflowRunSerializer(serializers.ModelSerializer):
    policy_name = serializers.CharField(source='policy.name', read_only=True)
    
    class Meta:
        model = WorkflowRun
        fields = [
            'id', 'policy', 'policy_name', 'status', 'total_patients',
            'candidates_found', 'flagged_count', 'precision', 'recall',
            'auto_actions', 'draft_actions', 'recommend_actions',
            'safety_flag_rate', 'duration_seconds', 'error_message',
            'created_at', 'updated_at',
        ]


class GovernanceRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = GovernanceRule
        fields = '__all__'


class ComplianceReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceReport
        fields = '__all__'


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class WorkflowTriggerSerializer(serializers.Serializer):
    policy_id = serializers.UUIDField(required=False)
    patient_limit = serializers.IntegerField(required=False, min_value=1, max_value=10000)


class WhatIfSerializer(serializers.Serializer):
    run_id = serializers.UUIDField()
    risk_review_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)
    draft_order_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)
    auto_order_threshold = serializers.FloatField(required=False, min_value=0, max_value=1)
    max_auto_actions_per_day = serializers.IntegerField(required=False, min_value=0)


class ReviewSerializer(serializers.Serializer):
    reviewed_by = serializers.CharField(max_length=200)
    review_notes = serializers.CharField(allow_blank=True)
    override_action = serializers.ChoiceField(
        choices=['NO_ACTION', 'RECOMMEND_NEURO_REVIEW', 'DRAFT_MRI_ORDER', 'AUTO_ORDER_MRI_AND_NOTIFY_NEURO'],
        required=False
    )

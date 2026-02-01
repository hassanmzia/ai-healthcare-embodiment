import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Card, CircularProgress, TextField, MenuItem,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TablePagination, Chip,
} from '@mui/material';
import { getAuditLogs } from '../services/api';
import { formatDate } from '../utils/helpers';
import type { AuditLog } from '../types';

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState('');

  useEffect(() => {
    setLoading(true);
    const params: Record<string, any> = { page: page + 1, page_size: rowsPerPage };
    if (typeFilter) params.action_type = typeFilter;
    getAuditLogs(params)
      .then((r) => { setLogs(r.data.results); setTotal(r.data.count); })
      .finally(() => setLoading(false));
  }, [page, rowsPerPage, typeFilter]);

  const typeColors: Record<string, any> = {
    AGENT_RUN: 'primary', DECISION: 'info', POLICY_CHANGE: 'warning',
    MANUAL_REVIEW: 'success', OVERRIDE: 'error', ALERT: 'error', EXPORT: 'default',
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Audit Trail</Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        Complete audit log of all system actions, decisions, and reviews
      </Typography>

      <Card sx={{ mb: 2 }}>
        <Box sx={{ p: 2 }}>
          <TextField select label="Action Type" value={typeFilter} size="small" sx={{ minWidth: 200 }}
            onChange={(e) => { setTypeFilter(e.target.value); setPage(0); }}>
            <MenuItem value="">All Types</MenuItem>
            <MenuItem value="AGENT_RUN">Agent Run</MenuItem>
            <MenuItem value="DECISION">Decision</MenuItem>
            <MenuItem value="POLICY_CHANGE">Policy Change</MenuItem>
            <MenuItem value="MANUAL_REVIEW">Manual Review</MenuItem>
            <MenuItem value="OVERRIDE">Override</MenuItem>
            <MenuItem value="ALERT">Alert</MenuItem>
          </TextField>
        </Box>
      </Card>

      <Card>
        <TableContainer>
          {loading ? <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box> : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Timestamp</TableCell>
                  <TableCell>Action Type</TableCell>
                  <TableCell>Actor</TableCell>
                  <TableCell>Target</TableCell>
                  <TableCell>Details</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {logs.map((log) => (
                  <TableRow key={log.id} hover>
                    <TableCell sx={{ fontSize: '0.8rem', whiteSpace: 'nowrap' }}>{formatDate(log.created_at)}</TableCell>
                    <TableCell><Chip label={log.action_type} size="small" color={typeColors[log.action_type] || 'default'} /></TableCell>
                    <TableCell>{log.actor}</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {log.target_type}{log.target_id ? `:${log.target_id.slice(0, 8)}` : ''}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.8rem' }}>
                      {JSON.stringify(log.details)}
                    </TableCell>
                  </TableRow>
                ))}
                {logs.length === 0 && (
                  <TableRow><TableCell colSpan={5} align="center" sx={{ py: 3 }}>No audit logs yet</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </TableContainer>
        <TablePagination
          rowsPerPageOptions={[10, 25, 50]} component="div" count={total}
          rowsPerPage={rowsPerPage} page={page}
          onPageChange={(_, p) => setPage(p)}
          onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value)); setPage(0); }}
        />
      </Card>
    </Box>
  );
}

import { useEffect, useState } from "react";
import {
  Box,
  Button,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import * as tauriApi from "../api/tauri";

export default function DatabaseExplorerView() {
  const [tables, setTables] = useState<string[]>([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [sql, setSql] = useState("SELECT * FROM agent_runs LIMIT 20");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    tauriApi.dbListTables().then(setTables).catch(() => {});
  }, []);

  const runQuery = async () => {
    setError(null);
    try {
      const result = await tauriApi.dbQuery(sql);
      setRows(result as unknown as Record<string, unknown>[]);
    } catch (e) {
      setError(String(e));
      setRows([]);
    }
  };

  const browseTable = (name: string) => {
    setSelectedTable(name);
    setSql(`SELECT * FROM ${name} LIMIT 50`);
  };

  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Table list */}
      <Box
        sx={{
          width: 180,
          borderRight: 1,
          borderColor: "divider",
          overflowY: "auto",
          p: 1,
        }}
      >
        <Typography variant="caption" color="text.secondary">
          Tables
        </Typography>
        {tables.map((t) => (
          <Button
            key={t}
            size="small"
            fullWidth
            variant={selectedTable === t ? "contained" : "text"}
            onClick={() => browseTable(t)}
            sx={{ justifyContent: "flex-start", textTransform: "none", mb: 0.25 }}
          >
            {t}
          </Button>
        ))}
      </Box>

      {/* Query area */}
      <Box
        sx={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          p: 1.5,
          overflow: "hidden",
        }}
      >
        <TextField
          fullWidth
          multiline
          rows={3}
          size="small"
          label="SQL"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          inputProps={{ style: { fontFamily: "monospace", fontSize: 12 } }}
          sx={{ mb: 1 }}
        />
        <Button
          size="small"
          variant="contained"
          onClick={runQuery}
          sx={{ alignSelf: "flex-start", mb: 1 }}
        >
          Run
        </Button>

        {error && (
          <Typography color="error" variant="body2" mb={1}>
            {error}
          </Typography>
        )}

        <TableContainer component={Paper} variant="outlined" sx={{ flex: 1, overflow: "auto" }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {columns.map((c) => (
                  <TableCell key={c} sx={{ fontWeight: 600 }}>
                    {c}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, i) => (
                <TableRow key={i} hover>
                  {columns.map((c) => (
                    <TableCell key={c}>
                      <Typography
                        variant="body2"
                        fontFamily="monospace"
                        noWrap
                        maxWidth={200}
                        title={String(row[c])}
                      >
                        {String(row[c] ?? "")}
                      </Typography>
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={columns.length || 1}>
                    <Typography variant="body2" color="text.secondary" align="center">
                      No results
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
    </Box>
  );
}

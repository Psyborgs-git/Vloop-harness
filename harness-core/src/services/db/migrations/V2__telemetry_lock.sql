-- V2: Immutable telemetry triggers

CREATE TRIGGER IF NOT EXISTS telemetry_immutable
BEFORE DELETE ON telemetry
BEGIN
  SELECT RAISE(ABORT, 'telemetry rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS telemetry_no_update
BEFORE UPDATE ON telemetry
BEGIN
  SELECT RAISE(ABORT, 'telemetry rows are immutable');
END;

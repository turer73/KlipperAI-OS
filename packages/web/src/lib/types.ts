// ═══════════════════════════════════════════════
// KlipperOS-AI Dashboard — Type Definitions
// Tum API response modelleri
// ═══════════════════════════════════════════════

// -- Auth --
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
}

// -- Printer --
export interface PrintStatus {
  state: string;
  filename: string | null;
  progress: number;
  print_duration: number;
  total_duration: number;
  filament_used: number;
  current_layer: number | null;
  total_layers: number | null;
}

export interface TemperatureReading {
  extruder_current: number;
  extruder_target: number;
  bed_current: number;
  bed_target: number;
  mcu_temperature: number | null;
}

// -- System --
export interface SystemInfo {
  cpu_percent: number;
  ram_used_mb: number;
  ram_total_mb: number;
  disk_used_gb: number;
  disk_total_gb: number;
  uptime_seconds: number;
}

export interface ServiceStatus {
  name: string;
  active: boolean;
  enabled: boolean;
  memory_mb: number;
}

// -- FlowGuard --
export interface FlowGuardStatus {
  verdict: string;
  filament_detected: boolean;
  heater_duty: number;
  tmc_sg_result: number | null;
  ai_class: string | null;
  current_layer: number | null;
  z_height: number | null;
}

// -- Calibration --
export interface CalibrationStatus {
  running: boolean;
  current_step: string;
  progress_percent: number;
  error: string | null;
  steps: Record<string, { status: string; result?: unknown }>;
}

export interface CalibStartRequest {
  extruder_temp?: number;
  bed_temp?: number;
  skip_pid?: boolean;
  skip_shaper?: boolean;
  skip_pa?: boolean;
  skip_flow?: boolean;
  pa_start?: number;
  pa_end?: number;
  pa_step?: number;
}

// -- Notifications --
export interface NotificationConfig {
  telegram: {
    enabled: boolean;
    bot_token: string;
    chat_id: string;
    min_severity: string;
  };
  discord: {
    enabled: boolean;
    webhook_url: string;
    min_severity: string;
  };
  cooldown_seconds: number;
}

// -- Recovery --
export interface RecoveryStatus {
  enabled: boolean;
  active_recovery: string | null;
  attempt_counts: Record<string, number>;
}

// -- Maintenance --
export interface MaintenanceAlert {
  component: string;
  severity: string;
  message: string;
  hours_used: number;
  limit_hours: number;
}

// -- Resource --
export interface ResourceMetric {
  timestamp: number;
  cpu_percent: number;
  ram_used_mb: number;
  cpu_temp: number | null;
}

// -- WebSocket --
export interface PrinterUpdate {
  type: "printer_update";
  data: {
    print_stats: Record<string, unknown>;
    extruder: Record<string, unknown>;
    heater_bed: Record<string, unknown>;
    display_status: Record<string, unknown>;
  };
}

// -- GCode Files --
export interface GCodeFile {
  filename: string;
  size: number;
  modified: number;
}

// -- Bambu Lab --
export interface BambuPrinter {
  id: string;
  name: string;
  hostname: string;
  serial: string;
  enabled: boolean;
  check_interval: number;
}

export interface BambuPrinterAdd {
  name: string;
  hostname: string;
  access_code: string;
  serial: string;
  enabled?: boolean;
  check_interval?: number;
}

export interface BambuOverview {
  monitor_running: boolean;
  printers: BambuPrinterStats[] | BambuPrinterBrief[];
  active_count?: number;
}

export interface BambuPrinterBrief {
  id: string;
  name: string;
  enabled: boolean;
}

export interface BambuPrinterStats {
  printer_name: string;
  printer_type: string;
  cycle_count: number;
  error_count: number;
  consecutive_alerts: number;
  is_printing: boolean;
  capture_stats: Record<string, unknown>;
}

export interface BambuPrinterStatus {
  id: string;
  name: string;
  printer_type: string;
  is_printing: boolean;
  state: string;
  progress_percent: number;
  nozzle_temp: number;
  nozzle_target: number;
  bed_temp: number;
  bed_target: number;
  current_layer: number;
  total_layers: number;
  filename: string;
  remaining_minutes: number;
  mqtt_connected: boolean;
  camera_connected: boolean;
}

export interface BambuDetection {
  printer_id: string;
  printer_type: string;
  detection_class: string;
  confidence: number;
  action: string;
  scores: Record<string, number>;
  timestamp: number;
}

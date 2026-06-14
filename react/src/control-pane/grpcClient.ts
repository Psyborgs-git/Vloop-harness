import { createPromiseClient } from "@connectrpc/connect";
import { createGrpcWebTransport } from "@connectrpc/connect-web";
import { SystemService } from "../gen/system_connect";
import { VaultService } from "../gen/vault_connect";
import { TerminalService } from "../gen/terminal_connect";
import { SandboxService } from "../gen/sandbox_connect";
import { ProcessManagerService } from "../gen/process_connect";
import { invoke } from "@tauri-apps/api/core";

export let systemClient: any = null;
export let vaultClient: any = null;
export let terminalClient: any = null;
export let sandboxClient: any = null;
export let processClient: any = null;

export async function initGrpcClient() {
  let grpcPort = 9102; // Fallback
  try {
    const config: any = await invoke("get_harness_config");
    if (config && config.grpc_port) {
      grpcPort = config.grpc_port;
    } else if (config && config.api_url) {
      const url = new URL(config.api_url);
      const backendPort = parseInt(url.port, 10);
      grpcPort = backendPort + 2;
    }
  } catch (e) {
    console.warn("Failed to get harness config from Tauri, using fallback port", e);
  }
  
  const transport = createGrpcWebTransport({
    baseUrl: `http://127.0.0.1:${grpcPort}`,
  });

  systemClient = createPromiseClient(SystemService, transport);
  vaultClient = createPromiseClient(VaultService, transport);
  terminalClient = createPromiseClient(TerminalService, transport);
  sandboxClient = createPromiseClient(SandboxService, transport);
  processClient = createPromiseClient(ProcessManagerService, transport);
}

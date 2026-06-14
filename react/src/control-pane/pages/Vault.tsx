import { useEffect, useState } from "react";
import { vaultClient } from "../grpcClient";
import { VaultKey } from "../../gen/vault_pb";
import { Trash2, Plus } from "lucide-react";

export default function VaultPage() {
  const [keys, setKeys] = useState<VaultKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState("");

  const fetchKeys = async () => {
    try {
      const res = await vaultClient.listKeys({});
      setKeys(res.keys);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName || !newKeyValue) return;
    try {
      await vaultClient.setKey({ key: newKeyName, value: newKeyValue });
      setNewKeyName("");
      setNewKeyValue("");
      fetchKeys();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDelete = async (key: string) => {
    try {
      await vaultClient.deleteKey({ key });
      fetchKeys();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="animate-fade-in">
      <h1 style={{ marginBottom: "8px" }}>Secure Vault</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: "32px" }}>Store credentials and secrets securely in memory.</p>

      <div className="glass-panel" style={{ padding: "24px", maxWidth: "800px", marginBottom: "32px" }}>
        <form onSubmit={handleAdd} style={{ display: "flex", gap: "16px", alignItems: "flex-end" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Key Name</label>
            <input 
              type="text" 
              value={newKeyName} 
              onChange={e => setNewKeyName(e.target.value)}
              placeholder="e.g. AWS_ACCESS_KEY"
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>
          <div style={{ flex: 2, display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Secret Value</label>
            <input 
              type="password" 
              value={newKeyValue} 
              onChange={e => setNewKeyValue(e.target.value)}
              placeholder="••••••••••••••••"
              style={{ padding: "10px", borderRadius: "8px", background: "var(--bg-primary)", color: "white", border: "1px solid var(--border-color)" }}
            />
          </div>
          <button 
            type="submit" 
            style={{
              background: "var(--bg-glass-hover)",
              color: "var(--text-primary)",
              padding: "10px 16px",
              borderRadius: "8px",
              border: "1px solid var(--border-color)",
              display: "flex",
              alignItems: "center",
              gap: "8px"
            }}
          >
            <Plus size={18} /> Add Secret
          </button>
        </form>
      </div>

      <div className="glass-panel" style={{ padding: "24px", maxWidth: "800px" }}>
        <h3 style={{ marginBottom: "16px", fontSize: "1.1rem" }}>Stored Secrets</h3>
        {keys.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)" }}>No secrets found in the vault.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {keys.map((k) => (
              <div key={k.key} style={{ 
                display: "flex", justifyContent: "space-between", alignItems: "center", 
                padding: "16px", background: "var(--bg-primary)", borderRadius: "8px", border: "1px solid var(--border-color)" 
              }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{k.key}</div>
                  <div style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "4px" }}>••••••••</div>
                </div>
                <button 
                  onClick={() => handleDelete(k.key)}
                  style={{ color: "#ef4444", padding: "8px" }}
                  title="Delete Secret"
                >
                  <Trash2 size={20} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

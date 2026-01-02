import React from "react";

export const LiveModeHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">🔴 O que é o Modo LIVE?</h3>
      <p>
        O <strong>Modo LIVE</strong> permite executar transações reais no mercado.
        Quando ativo, os agentes e o DEX Sniper executam operações com dinheiro real.
      </p>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">🔵 Paper vs 🔴 Live</h3>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div className="bg-blue-500/10 border border-blue-500/30 p-3 rounded-lg">
          <h4 className="font-semibold text-blue-400 mb-2">PAPER Mode</h4>
          <ul className="space-y-1">
            <li>• Simula transações</li>
            <li>• Sem risco de perda</li>
            <li>• PnL fictício</li>
            <li>• Ideal para aprender</li>
          </ul>
        </div>
        <div className="bg-red-500/10 border border-red-500/30 p-3 rounded-lg">
          <h4 className="font-semibold text-red-400 mb-2">LIVE Mode</h4>
          <ul className="space-y-1">
            <li>• Executa transações reais</li>
            <li>• Risco de perda real</li>
            <li>• Requer API keys / carteira</li>
            <li>• Lucros/perdas reais</li>
          </ul>
        </div>
      </div>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">⚙️ Toggles Disponíveis</h3>
      <ul className="space-y-3">
        <li>
          <strong>CEX Live Trading</strong>
          <p className="text-sm text-zinc-400">
            Ativa trading real na Kraken. Requer API Key e Secret configurados.
          </p>
        </li>
        <li>
          <strong>DEX Live Trading</strong>
          <p className="text-sm text-zinc-400">
            Ativa trading real na PancakeSwap via MetaMask. 
            Transações on-chain com BNB real.
          </p>
        </li>
        <li>
          <strong>Approval Mode</strong>
          <p className="text-sm text-zinc-400">
            Quando ON: todas as operações requerem aprovação manual.
            Recomendado ON especialmente em modo LIVE.
          </p>
        </li>
      </ul>
    </section>

    <section className="bg-red-500/10 border border-red-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-red-400 mb-2">⚠️ Antes de Ativar LIVE</h3>
      <ol className="list-decimal list-inside space-y-2 text-sm">
        <li><strong>Testa extensivamente</strong> em Paper mode primeiro</li>
        <li><strong>Começa com montantes mínimos</strong> (€5-10 por trade)</li>
        <li><strong>Verifica os Risk Settings</strong> (max loss diário, kill switch)</li>
        <li><strong>Mantém Approval Mode ON</strong> para aprovar cada trade</li>
        <li><strong>Monitoriza ativamente</strong> as primeiras operações</li>
        <li><strong>Nunca invistas</strong> mais do que podes perder</li>
      </ol>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Recomendação</h3>
      <p className="text-sm">
        Faz pelo menos <strong>1 semana de paper trading</strong> com bons resultados 
        antes de considerar o modo LIVE. Analisa os relatórios de performance e 
        ajusta os parâmetros até estares confiante.
      </p>
    </section>
  </div>
);

export const LiveModeTooltips = {
  cex_toggle: "Ativa/desativa trading real na exchange CEX (Kraken).",
  dex_toggle: "Ativa/desativa trading real na DEX (PancakeSwap via MetaMask).",
  approval_mode: "Quando ON, todos os trades requerem aprovação manual antes de executar.",
  paper_mode: "Modo de simulação. Não executa transações reais.",
  live_mode: "Modo de produção. Executa transações reais com dinheiro real.",
};

export default { LiveModeHelpContent, LiveModeTooltips };

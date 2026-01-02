import React from "react";

export const SwapsHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">📝 Estados dos Swap Plans</h3>
      <ul className="space-y-2">
        <li>
          <span className="inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-yellow-400"></span>
            <strong>PENDING</strong>
          </span>
          <p className="ml-4 text-sm text-zinc-400">Aguarda aprovação manual</p>
        </li>
        <li>
          <span className="inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400"></span>
            <strong>APPROVED</strong>
          </span>
          <p className="ml-4 text-sm text-zinc-400">Aprovado, pronto para executar</p>
        </li>
        <li>
          <span className="inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-400"></span>
            <strong>REJECTED</strong>
          </span>
          <p className="ml-4 text-sm text-zinc-400">Rejeitado pelo utilizador</p>
        </li>
        <li>
          <span className="inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400"></span>
            <strong>SUBMITTED</strong>
          </span>
          <p className="ml-4 text-sm text-zinc-400">Transação enviada, aguarda confirmação</p>
        </li>
        <li>
          <span className="inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500"></span>
            <strong>CONFIRMED</strong>
          </span>
          <p className="ml-4 text-sm text-zinc-400">Transação confirmada on-chain</p>
        </li>
        <li>
          <span className="inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500"></span>
            <strong>FAILED</strong>
          </span>
          <p className="ml-4 text-sm text-zinc-400">Transação falhou (revertida)</p>
        </li>
      </ul>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">🔄 Ações Disponíveis</h3>
      <ul className="space-y-2 text-sm">
        <li><strong>Approve:</strong> Aprova um plano PENDING</li>
        <li><strong>Reject:</strong> Rejeita um plano PENDING</li>
        <li><strong>Simulate:</strong> Executa em modo paper (não on-chain)</li>
        <li><strong>Send TX:</strong> Envia via MetaMask (requer LIVE mode)</li>
      </ul>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Dica</h3>
      <p className="text-sm">
        Em modo <span className="text-blue-400">PAPER</span>, usa "Simulate" para testar.
        O sistema cria uma posição simulada com PnL fictício.
      </p>
    </section>
  </div>
);

export const SwapsTooltips = {
  token: "Token que vais comprar com BNB.",
  amount: "Quantidade de BNB a gastar neste swap.",
  risk_score: "Score de risco do token (0-100). Maior = mais seguro.",
  status: "Estado atual do plano de swap.",
  tx_hash: "Hash da transação. Clica para ver no BSCScan.",
};

export default { SwapsHelpContent, SwapsTooltips };

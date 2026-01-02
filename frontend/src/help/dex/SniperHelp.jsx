import React from "react";

export const SniperHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">🎯 O que é o DEX Sniper?</h3>
      <p>
        O <strong>DEX Sniper</strong> deteta automaticamente novos pares de trading na PancakeSwap,
        avalia o risco de cada token, e cria planos de swap para aprovação.
      </p>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">🔄 Fluxo Completo (Passo-a-Passo)</h3>
      <ol className="list-decimal list-inside space-y-3">
        <li>
          <strong>Scan Pairs</strong> → Busca novos pares na DEXScreener
          <p className="ml-6 text-sm text-zinc-400">Filtra por liquidez, volume e idade</p>
        </li>
        <li>
          <strong>Score Token</strong> → Avalia risco (0-100)
          <p className="ml-6 text-sm text-zinc-400">Verifica honeypot, tax, liquidez, holders</p>
        </li>
        <li>
          <strong>Create Swap Plan</strong> → Estado: PENDING
          <p className="ml-6 text-sm text-zinc-400">Define montante, slippage, take profit, stop loss</p>
        </li>
        <li>
          <strong>Approve</strong> → Estado: APPROVED
          <p className="ml-6 text-sm text-zinc-400">Revisão manual antes de executar</p>
        </li>
        <li>
          <strong>Execute</strong>:
          <ul className="ml-6 text-sm space-y-1">
            <li>• <span className="text-blue-400">PAPER</span>: Simula a transação</li>
            <li>• <span className="text-red-400">LIVE</span>: Abre MetaMask para assinar</li>
          </ul>
        </li>
        <li>
          <strong>Monitor TX</strong> → SUBMITTED → CONFIRMED/FAILED
          <p className="ml-6 text-sm text-zinc-400">Acompanha o estado da transação on-chain</p>
        </li>
        <li>
          <strong>Sell (Fechar Posição)</strong>:
          <ul className="ml-6 text-sm space-y-1">
            <li>• Approve ERC20 → Permite router gastar tokens</li>
            <li>• Sell TX → Troca tokens por BNB</li>
            <li>• Close Position → Calcula PnL final</li>
          </ul>
        </li>
      </ol>
    </section>

    <section className="bg-green-500/10 border border-green-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-green-400 mb-2">✅ Regras de Ouro</h3>
      <ul className="space-y-2 text-sm">
        <li>• <strong>Slippage baixo</strong> (1-3%) para evitar sandwich attacks</li>
        <li>• <strong>Liquidez mínima</strong> $20k+ para evitar rug pulls</li>
        <li>• <strong>Score &gt; 50</strong> para filtrar honeypots</li>
        <li>• <strong>Approval sempre ON</strong> em modo live</li>
        <li>• <strong>Poucos trades/dia</strong> (1-3 máx) para gerir risco</li>
        <li>• <strong>Montantes pequenos</strong> (€5-15) até ganhar confiança</li>
      </ul>
    </section>

    <section className="bg-red-500/10 border border-red-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-red-400 mb-2">⚠️ Riscos DEX</h3>
      <ul className="space-y-1 text-sm">
        <li>• <strong>Honeypots:</strong> Tokens que não permitem venda</li>
        <li>• <strong>High Tax:</strong> Tokens com 50%+ de taxa de venda</li>
        <li>• <strong>Rug Pulls:</strong> Desenvolvedores removem liquidez</li>
        <li>• <strong>MEV/Sandwich:</strong> Bots que front-run transações</li>
      </ul>
      <p className="mt-2 text-xs text-zinc-400">
        O scanner tenta detetar estes problemas, mas não é 100% garantido.
        <strong> Nunca invistas mais do que podes perder.</strong>
      </p>
    </section>
  </div>
);

export const SniperPresets = {
  conservative: {
    tooltip: "Máxima segurança: alta liquidez, score alto, poucos trades",
    values: {
      min_liquidity_usd: 50000,
      min_volume_24h_usd: 20000,
      max_age_hours: 12,
      min_risk_score: 75,
      slippage_pct: 1,
      trade_size_eur: 5,
      max_daily_trades: 1,
    },
  },
  moderate: {
    tooltip: "Equilíbrio entre oportunidades e segurança",
    values: {
      min_liquidity_usd: 20000,
      min_volume_24h_usd: 10000,
      max_age_hours: 6,
      min_risk_score: 65,
      slippage_pct: 2,
      trade_size_eur: 10,
      max_daily_trades: 2,
    },
  },
  aggressive: {
    tooltip: "Mais oportunidades, mais risco. Pares novos, score mais baixo.",
    values: {
      min_liquidity_usd: 10000,
      min_volume_24h_usd: 5000,
      max_age_hours: 2,
      min_risk_score: 50,
      slippage_pct: 4,
      trade_size_eur: 15,
      max_daily_trades: 3,
    },
  },
};

export const SniperTooltips = {
  min_liquidity: "Liquidez mínima do par em USD. Maior = menos risco de rug pull.",
  min_volume: "Volume mínimo 24h em USD. Indica atividade e interesse no token.",
  max_age: "Idade máxima do par em horas. Pares novos = mais arriscados.",
  min_score: "Score mínimo de risco (0-100). Maior = mais seguro.",
  slippage: "Tolerância de preço %. Menor = menos risco de sandwich.",
  trade_size: "Montante por trade em EUR. Começa pequeno!",
  max_trades: "Máximo de trades por dia. Limita a exposição diária.",
  scan_pairs: "Busca novos pares na DEXScreener. Atualiza a lista de pares.",
  run_once: "Executa um ciclo completo: scan → score → criar planos.",
  start_sniper: "Inicia o sniper em modo contínuo. Monitoriza automaticamente.",
  create_plan: "Cria um plano de swap para este token. Vai para aprovação.",
  approve: "Aprova o plano. Permite executar (simular ou enviar TX).",
  simulate: "Simula a transação em modo paper. Não executa on-chain.",
  send_tx: "Envia a transação via MetaMask. Requer LIVE mode ativo.",
};

export default { SniperHelpContent, SniperPresets, SniperTooltips };

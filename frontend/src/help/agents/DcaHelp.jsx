import React from "react";

export const DcaHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">O que é o DCA?</h3>
      <p>
        <strong>Dollar Cost Averaging (DCA)</strong> é uma estratégia de investimento que consiste em comprar 
        uma quantia fixa de um ativo em intervalos regulares, independentemente do preço. Isto reduz o 
        impacto da volatilidade e elimina a necessidade de "adivinhar" o timing do mercado.
      </p>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Como funciona este agente?</h3>
      <ol className="list-decimal list-inside space-y-2">
        <li>Define um <strong>intervalo</strong> (ex: a cada 24h)</li>
        <li>Define uma <strong>queda mínima</strong> para comprar no dip (ex: -5%)</li>
        <li>Define o <strong>montante por compra</strong> (ex: €2)</li>
        <li>O agente monitoriza o preço e compra automaticamente quando as condições são cumpridas</li>
      </ol>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Parâmetros</h3>
      <ul className="space-y-2">
        <li><strong>Intervalo:</strong> Tempo mínimo entre compras (6h, 12h, 24h)</li>
        <li><strong>Dip %:</strong> Queda necessária para ativar compra (ex: -3% = compra quando cai 3%)</li>
        <li><strong>Montante:</strong> Valor em EUR por compra</li>
        <li><strong>Máx. Compras/Dia:</strong> Limite diário de operações</li>
      </ul>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Dica</h3>
      <p>
        Para iniciantes, recomendamos começar com o preset <span className="text-green-400">Conservador</span>: 
        compras pequenas (€2) a cada 24h apenas quando há queda de 5%. Isto minimiza o risco enquanto aprende.
      </p>
    </section>
  </div>
);

export const DcaPresets = {
  conservative: {
    tooltip: "Compras pequenas, intervalos longos, apenas em quedas significativas",
    values: {
      interval_hours: 24,
      dip_percent: 5,
      trade_size_eur: 2,
      max_buys_day: 1,
    },
  },
  moderate: {
    tooltip: "Equilíbrio entre frequência e tamanho das compras",
    values: {
      interval_hours: 12,
      dip_percent: 3,
      trade_size_eur: 4,
      max_buys_day: 2,
    },
  },
  aggressive: {
    tooltip: "Compras frequentes, aproveita pequenas quedas",
    values: {
      interval_hours: 6,
      dip_percent: 2,
      trade_size_eur: 6,
      max_buys_day: 3,
    },
  },
};

export const DcaTooltips = {
  interval: "Tempo mínimo entre compras. Intervalos mais longos = menos exposição.",
  dip_percent: "Queda necessária para ativar compra. Maior % = menos compras mas melhores preços.",
  trade_size: "Valor em EUR por operação. Começe pequeno e aumente gradualmente.",
  max_buys: "Limite diário de compras. Protege contra dias de alta volatilidade.",
};

export default { DcaHelpContent, DcaPresets, DcaTooltips };

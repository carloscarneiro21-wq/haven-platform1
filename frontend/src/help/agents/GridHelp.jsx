import React from "react";

export const GridHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">O que é Grid Trading?</h3>
      <p>
        <strong>Grid Trading</strong> é uma estratégia que coloca ordens de compra e venda em intervalos 
        regulares ("grelha") acima e abaixo do preço atual. Lucra com as oscilações de preço dentro de um range.
      </p>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Como funciona?</h3>
      <ol className="list-decimal list-inside space-y-2">
        <li>Define um <strong>range</strong> (ex: ±10% do preço atual)</li>
        <li>Define o número de <strong>grids</strong> (linhas da grelha)</li>
        <li>O agente coloca ordens de compra abaixo do preço e venda acima</li>
        <li>Quando uma compra executa, coloca venda acima. E vice-versa.</li>
        <li>Lucro = diferença entre compras e vendas</li>
      </ol>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Parâmetros</h3>
      <ul className="space-y-2">
        <li><strong>Range %:</strong> Amplitude da grelha (ex: ±10% = preço pode variar 20%)</li>
        <li><strong>Nº Grids:</strong> Quantas linhas. Mais grids = mais trades pequenos</li>
        <li><strong>Capital:</strong> Montante total alocado ao agente</li>
      </ul>
    </section>

    <section className="bg-yellow-500/10 border border-yellow-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-yellow-400 mb-2">⚠️ Atenção</h3>
      <p>
        Grid trading funciona melhor em <strong>mercados laterais</strong> (ranging). 
        Em tendências fortes (bull/bear), pode acumular posições perdedoras. 
        Use stop-loss global no Risk Manager.
      </p>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Dica</h3>
      <p>
        Range mais apertado (±3-6%) com muitos grids (20-40) = mais trades, lucros menores por trade.
        Range mais largo (±10%) com menos grids (12) = menos trades, lucros maiores por trade.
      </p>
    </section>
  </div>
);

export const GridPresets = {
  conservative: {
    tooltip: "Range largo, poucos grids. Menos trades, mais segurança.",
    values: {
      range_percent: 10,
      num_grids: 12,
      trade_size_eur: 4,
    },
  },
  moderate: {
    tooltip: "Equilíbrio entre frequência e amplitude.",
    values: {
      range_percent: 6,
      num_grids: 20,
      trade_size_eur: 2.5,
    },
  },
  aggressive: {
    tooltip: "Range apertado, muitos grids. Trades frequentes em mercados calmos.",
    values: {
      range_percent: 3,
      num_grids: 40,
      trade_size_eur: 1.25,
    },
  },
};

export const GridTooltips = {
  range: "Amplitude da grelha em %. Range maior = menos risco de sair do range.",
  grids: "Número de linhas. Mais grids = trades mais pequenos e frequentes.",
  capital: "Capital total alocado. Será dividido pelos grids ativos.",
};

export default { GridHelpContent, GridPresets, GridTooltips };

import React from "react";

export const WalletHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">🦊 Conectar MetaMask</h3>
      <ol className="list-decimal list-inside space-y-2">
        <li>Clica em <span className="text-yellow-400">"Connect MetaMask"</span></li>
        <li>Aprova a conexão no popup da MetaMask</li>
        <li>Se não estiveres na BSC, clica em <span className="text-blue-400">"Switch to BSC"</span></li>
        <li>Se a BSC não estiver adicionada, aceita adicionar a rede</li>
      </ol>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">⛓️ Rede BSC (BNB Smart Chain)</h3>
      <ul className="space-y-2 text-sm">
        <li><strong>Chain ID:</strong> 56 (0x38)</li>
        <li><strong>RPC:</strong> https://bsc-dataseed.binance.org/</li>
        <li><strong>Moeda:</strong> BNB</li>
        <li><strong>Explorer:</strong> https://bscscan.com/</li>
      </ul>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">⛽ Necessário: BNB para Gas</h3>
      <p>
        Precisas de <strong>BNB na carteira</strong> para pagar as taxas de transação (gas).
        Recomendamos pelo menos <strong>0.01 BNB</strong> (~$6) para começar.
      </p>
      <p className="mt-2 text-sm text-zinc-400">
        Podes comprar BNB na Binance e transferir para a tua MetaMask via BSC.
      </p>
    </section>

    <section className="bg-red-500/10 border border-red-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-red-400 mb-2">⚠️ Erros Comuns</h3>
      <ul className="space-y-2 text-sm">
        <li><strong>"Insufficient funds"</strong> → Não tens BNB suficiente para gas</li>
        <li><strong>"User rejected"</strong> → Rejeitaste a transação na MetaMask</li>
        <li><strong>"Wrong network"</strong> → Muda para BSC (chain 56)</li>
        <li><strong>"Transaction failed"</strong> → Slippage muito baixo ou token problemático</li>
      </ul>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Segurança</h3>
      <ul className="space-y-1 text-sm">
        <li>• <strong>Nunca partilhes</strong> a tua seed phrase</li>
        <li>• Verifica sempre o endereço do contrato antes de aprovar</li>
        <li>• Começa com montantes pequenos para testar</li>
        <li>• Em modo <span className="text-blue-400">PAPER</span>, nada é executado on-chain</li>
      </ul>
    </section>
  </div>
);

export const WalletTooltips = {
  connect: "Conecta a tua carteira MetaMask para executar transações reais.",
  switch_bsc: "Muda para a rede BSC (BNB Smart Chain) onde funciona a PancakeSwap.",
  address: "O teu endereço de carteira. As transações são enviadas daqui.",
};

export default { WalletHelpContent, WalletTooltips };

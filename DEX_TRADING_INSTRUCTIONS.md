# 📖 Instruções DEX Trading On-Chain - HAVEN

## Visão Geral

O sistema DEX Trading do HAVEN suporta operações on-chain reais em múltiplas blockchains:

| Chain | DEX | Modo | Tokens Nativos |
|-------|-----|------|----------------|
| Ethereum | Uniswap V3 | Testnet (Sepolia) / Mainnet | ETH |
| BSC | PancakeSwap V2 | Testnet / Mainnet | BNB |
| Solana | Jupiter Aggregator | Devnet / Mainnet | SOL |

---

## 🔐 1. Configurar Wallet/RPC

### A) Frontend - MetaMask (Semi-Auto)

1. **Instalar MetaMask**: https://metamask.io/download/
2. **Criar/Importar Carteira**
3. **Adicionar Redes de Teste**:
   - **Sepolia**: Chain ID 11155111, RPC `https://rpc.sepolia.org`
   - **BSC Testnet**: Chain ID 97, RPC `https://data-seed-prebsc-1-s1.binance.org:8545`

4. **Obter Tokens de Teste**:
   - Sepolia ETH: https://sepoliafaucet.com/
   - BSC Testnet BNB: https://testnet.bnbchain.org/faucet-smart
   - Solana Devnet: https://faucet.solana.com/

### B) Backend - Private Key (Full-Auto)

Para sniping automático e execução instantânea:

```bash
# Adicionar no /app/backend/.env
DEX_PRIVATE_KEY=0x_sua_private_key_aqui

# NUNCA use a carteira principal!
# Crie uma carteira dedicada para trading automático
```

**Gerar nova carteira (Python):**
```python
from eth_account import Account
account = Account.create()
print(f"Address: {account.address}")
print(f"Private Key: {account.key.hex()}")
```

---

## ✍️ 2. Assinar Transações

### Modo Semi-Automático (Recomendado)

O utilizador aprova cada transação no MetaMask:

```javascript
// Frontend envia transação para MetaMask
const txHash = await window.ethereum.request({
  method: 'eth_sendTransaction',
  params: [{
    from: walletAddress,
    to: routerContract,
    data: swapData,
    value: amountInWei, // se for swap de ETH
  }],
});
```

### Modo Full-Auto (Sniping)

Backend assina e envia automaticamente:

```python
# Backend com web3.py
signed_tx = account.sign_transaction(tx_dict)
tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
```

---

## 💱 3. Swaps Reais

### Ethereum/BSC (EVM Chains)

**API Endpoint**: `POST /api/dex/swap/quote`

```json
{
  "chain": "ethereum_sepolia",
  "token_in": "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",
  "token_out": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
  "amount_in": "0.1",
  "slippage_pct": 0.5
}
```

**Executar Swap (Semi-Auto)**:
```bash
POST /api/dex/swap/build-transaction
# Retorna transação unsigned para assinar no MetaMask
```

**Executar Swap (Full-Auto)**:
```bash
POST /api/dex/swap/execute
# Backend executa diretamente (requer DEX_PRIVATE_KEY)
```

### Solana (Jupiter)

Jupiter agrega liquidez de múltiplos DEXs (Raydium, Orca, etc.):

```python
# Obter quote
quote = await jupiter.get_quote(
    input_mint="So11111111111111111111111111111111111111112",  # SOL
    output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
    amount=100000000,  # 0.1 SOL em lamports
    slippage_bps=50,   # 0.5%
)

# Executar swap
result = await jupiter.execute_swap(quote, user_pubkey)
```

---

## 🎯 4. DEX Sniping Real

### Configuração do Sniper

```json
POST /api/dex/sniper/config
{
  "enabled": true,
  "chain": "ethereum_sepolia",
  "buy_amount_eth": 0.01,
  "max_slippage_pct": 10.0,
  "min_liquidity_usd": 1000,
  "max_buy_tax_pct": 10.0,
  "max_sell_tax_pct": 10.0,
  "auto_sell_enabled": true,
  "auto_sell_profit_pct": 100,
  "auto_sell_loss_pct": 50,
  "blacklisted_tokens": []
}
```

### Iniciar Monitoramento

```bash
POST /api/dex/sniper/start
{
  "chains": ["ethereum_sepolia", "bsc_testnet"]
}
```

### Como Funciona o Sniping

1. **Monitoramento**: O sistema monitora eventos `PairCreated` nos contratos Factory (Uniswap, PancakeSwap)

2. **Detecção**: Quando uma nova pool é criada:
   - Verifica liquidez mínima
   - Analisa contrato do token (honeypot check)
   - Avalia taxas de compra/venda

3. **Execução**: Se passar todos os checks:
   - Constrói transação de swap
   - Assina com private key do backend
   - Envia com gas prioritário
   - Registra execução no MongoDB

4. **Auto-Sell** (opcional):
   - Monitora preço do token
   - Vende automaticamente em +100% (take profit)
   - Vende automaticamente em -50% (stop loss)

---

## ⚠️ Avisos de Segurança

### Riscos do Trading On-Chain

1. **MEV/Sandwich Attacks**: Bots podem front-run transações
2. **Honeypots**: Tokens que não permitem venda
3. **Rug Pulls**: Desenvolvedores removem liquidez
4. **Gas Wars**: Custos elevados durante alta volatilidade
5. **Smart Contract Bugs**: Vulnerabilidades no código

### Mitigações Implementadas

- ✅ Análise de token antes de comprar
- ✅ Verificação de liquidez mínima
- ✅ Limites de taxa de imposto
- ✅ Slippage configurável
- ✅ Blacklist de tokens
- ✅ Stop-loss automático

### Boas Práticas

1. **Sempre teste em testnets primeiro**
2. **Use carteira dedicada (não a principal)**
3. **Comece com valores pequenos**
4. **Configure stop-loss**
5. **Monitore transações regularmente**

---

## 📁 Ficheiros de Referência

| Ficheiro | Descrição |
|----------|-----------|
| `/app/backend/services/dex/providers.py` | Configuração de chains e providers |
| `/app/backend/services/dex/uniswap.py` | Integração Uniswap V3 |
| `/app/backend/services/dex/pancakeswap.py` | Integração PancakeSwap |
| `/app/backend/services/dex/jupiter.py` | Integração Jupiter (Solana) |
| `/app/backend/services/dex/sniper.py` | Motor de sniping |
| `/app/backend/routes/dex_trading.py` | Endpoints da API |
| `/app/frontend/src/pages/DexTrading.jsx` | Interface do utilizador |

---

## 🚀 Próximos Passos

1. **Para Mainnet**: Adicionar RPC keys (Infura, Alchemy, Helius)
2. **Para Sniping**: Configurar `DEX_PRIVATE_KEY`
3. **Para Produção**: Implementar audit logs e alertas

---

*Documento criado em: 2025-12-31*
*Versão: 1.0*

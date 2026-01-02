# Telegram Notification Service
import os
import aiohttp
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Literal
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram bot for trading alerts and approval mode"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.pending_approvals: Dict[str, Dict] = {}
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)
    
    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict] = None
    ) -> bool:
        """Send a message to the configured chat"""
        if not self.is_configured():
            logger.warning("Telegram not configured, skipping notification")
            return False
        
        session = await self._get_session()
        
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        try:
            async with session.post(f"{self.base_url}/sendMessage", json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("ok", False)
                else:
                    error = await resp.text()
                    logger.error(f"Telegram API error: {error}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    # ==================== Alert Messages ====================
    
    async def send_trade_alert(
        self,
        agent_name: str,
        action: Literal["BUY", "SELL", "CLOSE"],
        symbol: str,
        amount: float,
        price: float,
        reason: str,
        pnl: Optional[float] = None
    ) -> bool:
        """Send trade entry/exit alert"""
        emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
        
        text = f"""
{emoji} <b>Trade Alert</b>

<b>Agent:</b> {agent_name}
<b>Action:</b> {action}
<b>Symbol:</b> {symbol}
<b>Amount:</b> {amount:.4f}
<b>Price:</b> ${price:,.2f}
"""
        
        if pnl is not None:
            pnl_emoji = "✅" if pnl >= 0 else "❌"
            text += f"<b>P&L:</b> {pnl_emoji} ${pnl:,.2f}\n"
        
        text += f"\n<i>{reason}</i>"
        
        return await self.send_message(text)
    
    async def send_kill_switch_alert(self, reason: str) -> bool:
        """Send emergency kill switch activation alert"""
        text = f"""
🚨 <b>EMERGENCY STOP ACTIVATED</b> 🚨

<b>All trading halted!</b>

<b>Reason:</b> {reason}
<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

⚠️ Manual review required before resuming.
"""
        return await self.send_message(text)
    
    async def send_circuit_breaker_alert(
        self,
        agent_name: str,
        reasons: List[str],
        cooldown_minutes: int
    ) -> bool:
        """Send circuit breaker trip alert"""
        text = f"""
⚡ <b>Circuit Breaker Tripped</b>

<b>Agent:</b> {agent_name}
<b>Reasons:</b>
"""
        for r in reasons:
            text += f"  • {r}\n"
        
        text += f"\n<b>Cooldown:</b> {cooldown_minutes} minutes"
        
        return await self.send_message(text)
    
    async def send_daily_summary(
        self,
        date: str,
        total_pnl: float,
        total_pnl_pct: float,
        trades_count: int,
        win_rate: float,
        max_drawdown: float,
        active_agents: int,
        top_agent: str,
        top_agent_pnl: float
    ) -> bool:
        """Send daily performance summary"""
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        
        text = f"""
📊 <b>Daily Summary - {date}</b>

{pnl_emoji} <b>Total P&L:</b> ${total_pnl:,.2f} ({total_pnl_pct:+.2f}%)
📋 <b>Trades:</b> {trades_count}
🎯 <b>Win Rate:</b> {win_rate:.1f}%
📉 <b>Max Drawdown:</b> {max_drawdown:.2f}%

<b>Active Agents:</b> {active_agents}
<b>Top Performer:</b> {top_agent} (${top_agent_pnl:+,.2f})
"""
        return await self.send_message(text)
    
    async def send_risk_warning(
        self,
        warning_type: str,
        current_value: float,
        threshold: float,
        details: str = ""
    ) -> bool:
        """Send risk threshold warning"""
        text = f"""
⚠️ <b>Risk Warning</b>

<b>Type:</b> {warning_type}
<b>Current:</b> {current_value:.2f}%
<b>Threshold:</b> {threshold:.2f}%

{details}
"""
        return await self.send_message(text)
    
    # ==================== Approval Mode ====================
    
    async def send_trade_approval_request(
        self,
        approval_id: str,
        agent_name: str,
        action: str,
        symbol: str,
        amount: float,
        price: float,
        reason: str,
        indicators: Dict = None
    ) -> bool:
        """Send trade suggestion for approval with inline buttons"""
        emoji = "🟢" if action == "BUY" else "🔴"
        
        text = f"""
{emoji} <b>Trade Suggestion - Awaiting Approval</b>

<b>Agent:</b> {agent_name}
<b>Action:</b> {action}
<b>Symbol:</b> {symbol}
<b>Amount:</b> {amount:.4f}
<b>Price:</b> ${price:,.2f}

<b>Reason:</b>
<i>{reason}</i>
"""
        
        if indicators:
            text += "\n<b>Indicators:</b>\n"
            for k, v in indicators.items():
                text += f"  • {k}: {v}\n"
        
        # Store pending approval
        self.pending_approvals[approval_id] = {
            "agent_name": agent_name,
            "action": action,
            "symbol": symbol,
            "amount": amount,
            "price": price,
            "created_at": datetime.now(timezone.utc)
        }
        
        # Inline keyboard with Approve/Reject buttons
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve_{approval_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject_{approval_id}"}
                ]
            ]
        }
        
        return await self.send_message(text, reply_markup=reply_markup)
    
    async def handle_callback(self, callback_data: str) -> Dict:
        """Handle callback from inline button press"""
        parts = callback_data.split("_", 1)
        if len(parts) != 2:
            return {"success": False, "error": "Invalid callback data"}
        
        action, approval_id = parts
        
        if approval_id not in self.pending_approvals:
            return {"success": False, "error": "Approval request expired or not found"}
        
        approval = self.pending_approvals.pop(approval_id)
        
        if action == "approve":
            return {
                "success": True,
                "approved": True,
                "approval_id": approval_id,
                "trade_details": approval
            }
        elif action == "reject":
            return {
                "success": True,
                "approved": False,
                "approval_id": approval_id,
                "trade_details": approval
            }
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    
    # ==================== Webhook Handler ====================
    
    async def process_update(self, update: Dict) -> Dict:
        """Process incoming Telegram update (webhook)"""
        # Handle callback queries (button presses)
        if "callback_query" in update:
            callback = update["callback_query"]
            callback_data = callback.get("data", "")
            
            result = await self.handle_callback(callback_data)
            
            # Answer callback to remove loading state
            await self._answer_callback(callback["id"], "✓" if result.get("approved") else "✗")
            
            # Log to database
            await self.db.telegram_callbacks.insert_one({
                "callback_id": callback["id"],
                "data": callback_data,
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return result
        
        # Handle text messages (commands)
        if "message" in update and "text" in update["message"]:
            text = update["message"]["text"]
            chat_id = update["message"]["chat"]["id"]
            
            if text == "/status":
                # Send current status
                await self._send_status()
            elif text == "/help":
                await self._send_help()
            elif text == "/stop":
                return {"command": "emergency_stop", "chat_id": chat_id}
            elif text == "/resume":
                return {"command": "resume_trading", "chat_id": chat_id}
        
        return {"success": True}
    
    async def _answer_callback(self, callback_id: str, text: str):
        """Answer callback query"""
        session = await self._get_session()
        try:
            await session.post(
                f"{self.base_url}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text}
            )
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")
    
    async def _send_status(self):
        """Send current bot status"""
        # This would fetch from database
        text = "📊 <b>Bot Status</b>\n\n<i>Fetching data...</i>"
        await self.send_message(text)
    
    async def _send_help(self):
        """Send help message"""
        text = """
🤖 <b>CryptoBot Commands</b>

/status - Current portfolio status
/stop - Emergency stop all trading
/resume - Resume trading
/help - Show this help

<b>Approval Mode:</b>
When enabled, trades will be sent for approval. Use the inline buttons to Approve or Reject.
"""
        await self.send_message(text)

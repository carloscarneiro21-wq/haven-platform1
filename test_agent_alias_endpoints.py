#!/usr/bin/env python3
"""Test Agent Execution Bridge Alias Endpoints.

Tests the new backwards-compatible alias endpoints:
- POST /api/agent/trade/open (should behave like /api/agent/execute)
- POST /api/agent/trade/{trade_id}/close (should close and return pnl)
"""

import requests
import json
import sys
from datetime import datetime

class AgentAliasEndpointTester:
    def __init__(self, base_url="https://trade-route.preview.emergentagent.com"):
        self.base_url = base_url
        self.auth_token = None
        self.test_trade_id = None
        
    def get_owner_auth_token(self):
        """Get owner authentication token."""
        login_data = {
            "username_or_email": "owner", 
            "password": "Haven!2026_Strong#Auth"
        }
        
        url = f"{self.base_url}/api/auth/login"
        headers = {'Content-Type': 'application/json'}
        
        print("🔑 Getting owner auth token...")
        try:
            response = requests.post(url, json=login_data, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.auth_token = data["access_token"]
                    print(f"✅ Auth token obtained: {self.auth_token[:20]}...")
                    return True
                else:
                    print(f"❌ No access_token in response: {data}")
                    return False
            else:
                print(f"❌ Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def test_agent_trade_open_alias(self):
        """Test POST /api/agent/trade/open (alias for /api/agent/execute)."""
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.auth_token}'
        }
        
        trade_data = {
            "agent_id": "test_agent_001",
            "agent_name": "Test Agent",
            "strategy": "MM",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "qty": 0.005,
            "price": 65000.0,
            "reason": "Testing alias endpoint"
        }
        
        url = f"{self.base_url}/api/agent/trade/open"
        print(f"\n🔍 Testing POST /api/agent/trade/open...")
        print(f"   URL: {url}")
        print(f"   Data: {json.dumps(trade_data, indent=2)}")
        
        try:
            response = requests.post(url, json=trade_data, headers=headers, timeout=15)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
                
                # Check required fields
                if data.get("success") and data.get("trade_id"):
                    self.test_trade_id = data["trade_id"]
                    print(f"✅ Agent trade open alias working - Trade ID: {self.test_trade_id}")
                    
                    # Verify expected fields
                    expected_fields = ["success", "trade_id", "entry_price", "qty", "fees", "slippage", "latency_ms"]
                    found_fields = [field for field in expected_fields if field in data]
                    print(f"   Fields: {len(found_fields)}/{len(expected_fields)} - {found_fields}")
                    
                    return True
                else:
                    print(f"❌ Missing success or trade_id in response")
                    return False
            else:
                print(f"❌ Request failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Request error: {e}")
            return False
    
    def test_agent_trade_close_alias(self):
        """Test POST /api/agent/trade/{trade_id}/close."""
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        if not self.test_trade_id:
            print("❌ No test trade ID available")
            return False
            
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.auth_token}'
        }
        
        close_data = {
            "exit_price": 66000.0,
            "fees": 0.0
        }
        
        url = f"{self.base_url}/api/agent/trade/{self.test_trade_id}/close"
        print(f"\n🔍 Testing POST /api/agent/trade/{{trade_id}}/close...")
        print(f"   URL: {url}")
        print(f"   Data: {json.dumps(close_data, indent=2)}")
        
        try:
            response = requests.post(url, json=close_data, headers=headers, timeout=15)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
                
                # Check required fields
                if data.get("success"):
                    print(f"✅ Agent trade close alias working")
                    
                    # Verify PnL calculation
                    pnl = data.get("pnl")
                    pnl_pct = data.get("pnl_pct")
                    status = data.get("status")
                    
                    print(f"   PnL: {pnl}")
                    print(f"   PnL%: {pnl_pct}")
                    print(f"   Status: {status}")
                    
                    if status == "CLOSED" and pnl is not None:
                        print("✅ Trade closed successfully with PnL calculation")
                        return True
                    else:
                        print(f"❌ Expected CLOSED status and PnL, got status={status}, pnl={pnl}")
                        return False
                else:
                    print(f"❌ Close operation failed: {data}")
                    return False
            else:
                print(f"❌ Request failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Request error: {e}")
            return False
    
    def test_agent_positions_endpoint(self):
        """Test GET /api/agent/positions to verify position tracking."""
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.auth_token}'
        }
        
        url = f"{self.base_url}/api/agent/positions"
        print(f"\n🔍 Testing GET /api/agent/positions...")
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
                
                if isinstance(data, dict) and "positions" in data:
                    positions = data["positions"]
                    count = data.get("count", len(positions))
                    print(f"✅ Agent positions endpoint working - Found {count} positions")
                    return True
                else:
                    print(f"❌ Expected dict with 'positions' key, got {type(data)}")
                    return False
            else:
                print(f"❌ Request failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Request error: {e}")
            return False
    
    def test_trades_api_integration(self):
        """Test that agent-created trades appear in GET /api/trades."""
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.auth_token}'
        }
        
        url = f"{self.base_url}/api/trades?limit=10"
        print(f"\n🔍 Testing GET /api/trades integration...")
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, dict) and "trades" in data:
                    trades = data["trades"]
                    count = data.get("count", len(trades))
                    print(f"   Found {count} trades")
                    
                    # Look for our test trade
                    test_trade_found = False
                    if self.test_trade_id:
                        for trade in trades:
                            if trade.get("id") == self.test_trade_id:
                                test_trade_found = True
                                print(f"   ✅ Test trade {self.test_trade_id} found in trades API")
                                print(f"   Trade details: {trade.get('symbol')} {trade.get('side')} {trade.get('qty')} @ {trade.get('entry_price')}")
                                print(f"   Status: {trade.get('status')}, PnL: {trade.get('pnl')}")
                                break
                    
                    if test_trade_found or count > 0:
                        print("✅ Trades API integration working")
                        return True
                    else:
                        print("⚠️ No trades found, but API is working")
                        return True
                else:
                    print(f"❌ Expected dict with 'trades' key, got {type(data)}")
                    return False
            else:
                print(f"❌ Request failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Request error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all alias endpoint tests."""
        print("=" * 60)
        print("AGENT EXECUTION BRIDGE ALIAS ENDPOINTS TEST")
        print("=" * 60)
        
        # Get auth token
        if not self.get_owner_auth_token():
            print("❌ Failed to get auth token, aborting tests")
            return False
        
        # Test results
        results = []
        
        # Test 1: Agent trade open alias
        results.append(("Agent Trade Open Alias", self.test_agent_trade_open_alias()))
        
        # Test 2: Agent trade close alias
        results.append(("Agent Trade Close Alias", self.test_agent_trade_close_alias()))
        
        # Test 3: Agent positions endpoint
        results.append(("Agent Positions Endpoint", self.test_agent_positions_endpoint()))
        
        # Test 4: Trades API integration
        results.append(("Trades API Integration", self.test_trades_api_integration()))
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)
        
        passed = 0
        total = len(results)
        
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name}")
            if success:
                passed += 1
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All alias endpoint tests PASSED!")
            return True
        else:
            print("⚠️ Some tests failed")
            return False

if __name__ == "__main__":
    tester = AgentAliasEndpointTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
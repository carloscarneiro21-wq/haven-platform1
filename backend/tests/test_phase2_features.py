"""
Comprehensive test suite for Crypto Trading System Phase 2 features.
Tests all the specific Phase 2 endpoints and functionality.
"""
import requests
import json
import uuid
from datetime import datetime

class Phase2FeatureTester:
    def __init__(self, base_url="https://trade-route.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.auth_token = None
        self.test_username = f"testuser_{uuid.uuid4().hex[:8]}"
        
    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        if headers is None:
            headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.failed_tests.append(f"{name}: Expected {expected_status}, got {response.status_code}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append(f"{name}: {str(e)}")
            return False, {}

    def test_health_endpoints(self):
        """Test all health and status endpoints"""
        print("\n📊 HEALTH & STATUS ENDPOINTS")
        print("-" * 40)
        
        # Test health endpoint
        self.run_test("Health Check", "GET", "health", 200)
        
        # Test heartbeat endpoint
        self.run_test("Heartbeat", "GET", "heartbeat", 200)
        
        # Test engine status
        self.run_test("Engine Status", "GET", "engine/status", 200)

    def test_authentication_flow(self):
        """Test complete authentication flow"""
        print("\n🔐 AUTHENTICATION ENDPOINTS")
        print("-" * 40)
        
        # Test user registration with unique username
        user_data = {
            "username": self.test_username,
            "password": "testpass123"
        }
        success, _ = self.run_test("User Registration", "POST", "auth/register", 200, data=user_data)
        
        if success:
            # Test login
            login_data = {
                "username": self.test_username,
                "password": "testpass123"
            }
            success, response_data = self.run_test("User Login", "POST", "auth/login", 200, data=login_data)
            
            if success and "access_token" in response_data:
                self.auth_token = response_data["access_token"]
                print(f"   🔑 Auth token obtained: {self.auth_token[:20]}...")
                
                # Test authenticated endpoint
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.auth_token}'
                }
                self.run_test("Get Current User", "GET", "auth/me", 200, headers=headers)

    def test_data_feed_health(self):
        """Test data feed health and market data endpoints"""
        print("\n📡 DATA FEED HEALTH")
        print("-" * 40)
        
        # Test market health
        self.run_test("Market Data Health", "GET", "market/health", 200)
        
        # Test BTC ticker
        self.run_test("BTC Ticker Data", "GET", "market/ticker/BTC-USDT", 200)

    def test_notification_endpoints(self):
        """Test notification configuration endpoints"""
        print("\n🔔 NOTIFICATION ENDPOINTS")
        print("-" * 40)
        
        # Test get notification config
        self.run_test("Get Notification Config", "GET", "notifications/config", 200)
        
        # Test update notification config
        config_data = {"enabled": False}
        self.run_test("Update Notification Config", "PUT", "notifications/config", 200, data=config_data)

    def test_stress_tests(self):
        """Test stress test functionality"""
        print("\n⚡ STRESS TESTS")
        print("-" * 40)
        
        # Test get stress test scenarios
        self.run_test("Get Stress Test Scenarios", "GET", "stress-tests/scenarios", 200)
        
        # Test run stress tests
        self.run_test("Run All Stress Tests", "POST", "stress-tests/run", 200)

    def test_dashboard_and_agents(self):
        """Test dashboard and agent endpoints"""
        print("\n📈 DASHBOARD & AGENTS")
        print("-" * 40)
        
        # Test dashboard
        self.run_test("Dashboard Data", "GET", "dashboard", 200)
        
        # Test agents - should return 3 agents (DCA, Grid, Trend)
        success, response_data = self.run_test("Get All Agents", "GET", "agents", 200)
        if success and isinstance(response_data, list):
            agent_types = [agent.get('type') for agent in response_data]
            expected_types = ['dca', 'grid', 'trend']
            if all(agent_type in agent_types for agent_type in expected_types):
                print(f"   ✅ All 3 expected agent types found: {agent_types}")
            else:
                print(f"   ⚠️  Expected agent types {expected_types}, found: {agent_types}")

    def test_runtime_control(self):
        """Test runtime control functionality"""
        print("\n🎮 RUNTIME CONTROL")
        print("-" * 40)
        
        # Test initial status
        self.run_test("Initial Runtime Status", "GET", "runtime/status", 200)
        
        # Test start runtime
        start_data = {"action": "start", "interval": 60}
        self.run_test("Start Runtime", "POST", "runtime/control", 200, data=start_data)
        
        # Test status after start
        success, response_data = self.run_test("Runtime Status After Start", "GET", "runtime/status", 200)
        if success and response_data.get("running") == True:
            print("   ✅ Runtime is now running")
        
        # Test stop runtime
        stop_data = {"action": "stop"}
        self.run_test("Stop Runtime", "POST", "runtime/control", 200, data=stop_data)

    def run_all_tests(self):
        """Run all Phase 2 feature tests"""
        print("🚀 Starting Crypto Trading System Phase 2 Feature Tests")
        print("=" * 60)
        
        # Run all test categories
        self.test_health_endpoints()
        self.test_authentication_flow()
        self.test_data_feed_health()
        self.test_notification_endpoints()
        self.test_stress_tests()
        self.test_dashboard_and_agents()
        self.test_runtime_control()
        
        # Print final results
        print("\n" + "=" * 60)
        print(f"📊 PHASE 2 TEST RESULTS: {self.tests_passed}/{self.tests_run} passed")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for failure in self.failed_tests:
                print(f"   - {failure}")
        else:
            print("\n✅ All Phase 2 tests passed!")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test runner"""
    tester = Phase2FeatureTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
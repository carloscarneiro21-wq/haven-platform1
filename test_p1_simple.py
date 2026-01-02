#!/usr/bin/env python3

import requests
import json

def test_p1_features():
    """Simple P1 feature test"""
    base_url = "https://trade-route.preview.emergentagent.com"
    
    # Login first
    print("🔐 Logging in...")
    login_data = {"username": "owner", "password": "Owner2025!Secure"}
    response = requests.post(f"{base_url}/api/auth/login", json=login_data)
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code}")
        return False
    
    token = response.json().get("access_token")
    print(f"✅ Login successful. Token: {token[:20]}...")
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    # Test P1.1 - Config Editor API Tests
    print("\n🔧 P1.1 - CONFIG EDITOR API TESTS")
    
    # 1. GET /api/config/system
    print("\n1. Testing GET /api/config/system")
    response = requests.get(f"{base_url}/api/config/system", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Config sections: {list(data.keys())}")
        print("   ✅ Config system GET working")
    else:
        print(f"   ❌ Config system GET failed: {response.text}")
    
    # 2. POST /api/config/system/diff
    print("\n2. Testing POST /api/config/system/diff")
    diff_data = {"updates": {"guardian.daily_loss_limit_pct": -1.5}}
    response = requests.post(f"{base_url}/api/config/system/diff", json=diff_data, headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Diffs count: {len(data.get('diffs', []))}")
        print("   ✅ Config system DIFF working")
    else:
        print(f"   ❌ Config system DIFF failed: {response.text}")
    
    # 3. GET /api/config/presets/mm
    print("\n3. Testing GET /api/config/presets/mm")
    response = requests.get(f"{base_url}/api/config/presets/mm", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   MM presets count: {len(data)}")
        print("   ✅ MM presets GET working")
    else:
        print(f"   ❌ MM presets GET failed: {response.text}")
    
    # 4. GET /api/config/presets/mom
    print("\n4. Testing GET /api/config/presets/mom")
    response = requests.get(f"{base_url}/api/config/presets/mom", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   MOM presets count: {len(data)}")
        print("   ✅ MOM presets GET working")
    else:
        print(f"   ❌ MOM presets GET failed: {response.text}")
    
    # Test P1.2 - Dashboard API Tests
    print("\n📊 P1.2 - DASHBOARD API TESTS")
    
    # 5. GET /api/growth/guardian/state (corrected endpoint)
    print("\n5. Testing GET /api/growth/guardian/state")
    response = requests.get(f"{base_url}/api/growth/guardian/state", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Guardian fields: {list(data.keys())}")
        print("   ✅ Guardian state GET working")
    else:
        print(f"   ❌ Guardian state GET failed: {response.text}")
    
    # 6. GET /api/growth/paper/pnl (corrected endpoint)
    print("\n6. Testing GET /api/growth/paper/pnl")
    response = requests.get(f"{base_url}/api/growth/paper/pnl", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   PnL data type: {type(data)}")
        print("   ✅ Growth PnL GET working")
    else:
        print(f"   ❌ Growth PnL GET failed: {response.text}")
    
    # Test P1.3 - Scheduler API Tests
    print("\n⏰ P1.3 - SCHEDULER API TESTS")
    
    # 7. GET /api/growth/run/schedule (corrected endpoint)
    print("\n7. Testing GET /api/growth/run/schedule")
    response = requests.get(f"{base_url}/api/growth/run/schedule", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Schedule config fields: {list(data.keys())}")
        print("   ✅ Schedule config GET working")
    else:
        print(f"   ❌ Schedule config GET failed: {response.text}")
    
    # 8. PUT /api/growth/scheduler/config (corrected endpoint)
    print("\n8. Testing PUT /api/growth/scheduler/config")
    schedule_data = {
        "enabled": False,
        "interval_minutes": 30,
        "symbols": ["BTC/USDT"],
        "active_hours_start": 9,
        "active_hours_end": 21,
        "active_days": [0, 1, 2, 3, 4]
    }
    response = requests.put(f"{base_url}/api/growth/scheduler/config", json=schedule_data, headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Update response: {data}")
        print("   ✅ Schedule config PUT working")
    else:
        print(f"   ❌ Schedule config PUT failed: {response.text}")
    
    print("\n✅ P1 Feature Tests Completed!")
    return True

if __name__ == "__main__":
    test_p1_features()
#!/usr/bin/env python3
"""Test P2.2 Data Feed Enhancement API endpoints."""

import requests
import json

BASE_URL = "https://trade-route.preview.emergentagent.com/api"

def test_api_endpoint(name, endpoint, expected_status=200):
    """Test a single API endpoint."""
    url = f"{BASE_URL}/{endpoint}"
    print(f"\n🔍 Testing {name}...")
    print(f"   URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        success = response.status_code == expected_status
        
        if success:
            print(f"✅ Passed - Status: {response.status_code}")
            try:
                data = response.json()
                return True, data
            except:
                return True, {}
        else:
            print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            return False, {}
            
    except Exception as e:
        print(f"❌ Failed - Error: {str(e)}")
        return False, {}

def main():
    print("🚀 Testing P2.2 Data Feed Enhancement API Endpoints")
    print("=" * 60)
    
    tests_passed = 0
    tests_total = 0
    
    # Test basic health
    tests_total += 1
    success, data = test_api_endpoint("Health Check", "health")
    if success:
        tests_passed += 1
        print(f"   Status: {data.get('status')}")
        print(f"   MongoDB: {data.get('mongodb')}")
        print(f"   Runtime: {data.get('runtime')}")
    
    # Test market health (should show data feed status)
    tests_total += 1
    success, data = test_api_endpoint("Market Health", "market/health")
    if success:
        tests_passed += 1
        health = data.get("health", {})
        print(f"   Primary source: {health.get('primary_source')}")
        print(f"   Active source: {health.get('active_source')}")
        print(f"   Using fallback: {health.get('using_fallback')}")
        
        sources = health.get("sources", {})
        print(f"   Available sources: {list(sources.keys())}")
        
        # Check if we have the expected 3 venues
        expected_venues = ["kraken", "binance", "coingecko"]
        found_venues = list(sources.keys())
        if all(venue in found_venues for venue in expected_venues):
            print("   ✅ All 3 expected venues (kraken, binance, coingecko) found")
        else:
            missing = set(expected_venues) - set(found_venues)
            print(f"   ⚠️ Missing venues: {missing}")
    
    # Test BTC ticker (should work with new data feed)
    tests_total += 1
    success, data = test_api_endpoint("BTC Ticker", "market/ticker/BTC-USDT")
    if success:
        tests_passed += 1
        last_price = data.get("last")
        bid = data.get("bid")
        ask = data.get("ask")
        print(f"   Last price: {last_price}")
        print(f"   Bid: {bid}")
        print(f"   Ask: {ask}")
        
        # Check if price is reasonable
        try:
            if last_price:
                price_float = float(last_price)
                if 30000 <= price_float <= 150000:
                    print(f"   ✅ BTC price ${price_float:,.2f} is reasonable")
                else:
                    print(f"   ⚠️ BTC price ${price_float:,.2f} seems unreasonable")
        except (ValueError, TypeError):
            print(f"   ⚠️ BTC price '{last_price}' is not a valid number")
    
    # Test dashboard (should include market data)
    tests_total += 1
    success, data = test_api_endpoint("Dashboard", "dashboard")
    if success:
        tests_passed += 1
        market_features = data.get("market_features", {})
        print(f"   Market features available for {len(market_features)} symbols")
        
        if "BTC/USDT" in market_features:
            btc_features = market_features["BTC/USDT"]
            btc_price = btc_features.get("last_price", 0)
            print(f"   BTC price from features: {btc_price}")
            if btc_price > 0:
                print("   ✅ BTC market features available")
            else:
                print("   ⚠️ BTC price is 0 (may be in safe mode)")
        else:
            print("   ⚠️ BTC/USDT not found in market features")
    
    # Print results
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {tests_passed}/{tests_total} passed")
    
    if tests_passed == tests_total:
        print("✅ All P2.2 Data Feed Enhancement tests passed!")
        return 0
    else:
        print(f"❌ {tests_total - tests_passed} tests failed")
        return 1

if __name__ == "__main__":
    exit(main())
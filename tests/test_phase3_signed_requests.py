#!/usr/bin/env python3
"""
Phase 3: Signed Request Through MCP Wrapper Test

Tests making properly signed requests to the MCP wrapper,
validating the complete security flow.
"""

import sys
import os
import json
import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'amorce_py_sdk'))

from amorce import IdentityManager

def test_signed_request_to_wrapper():
    """Test wrapper accepts signed requests and rejects unsigned ones."""
    
    print("\n" + "="*70)
    print("🧪 PHASE 3: SIGNED REQUEST TO MCP WRAPPER TEST")
    print("="*70)
    
    # Step 1: Create agent identity
    print("\n📍 Step 1: Create Agent Identity")
    identity = IdentityManager.generate_ephemeral()
    print(f"   ✅ Agent ID: {identity.agent_id}")
    print(f"   Public Key (first 50 chars): {identity.public_key_pem[:50]}...")
    
    # Step 2: Test unsigned request (should fail)
    print("\n📍 Step 2: Test Unsigned Request (Should Fail)")
    response = requests.post(
        "http://localhost:5001/v1/tools/list",
        json={"payload": {}}
    )
    
    if response.status_code == 401:
        print(f"   ✅ Correctly rejected unsigned request (401)")
        print(f"   Error: {response.json().get('error', '')[:80]}")
    else:
        print(f"   ❌ Expected 401, got {response.status_code}")
        return False
    
    # Step 3: Create signed request
    print("\n📍 Step 3: Create Properly Signed Request")
    
    payload = {"payload": {}}
    payload_json = json.dumps(payload, sort_keys=True)
    payload_bytes = payload_json.encode('utf-8')
    
    # Sign the payload using SDK method
    signature = identity.sign_data(payload_bytes)
    
    print(f"   Payload: {payload_json}")
    print(f"   Signature (first 50 chars): {signature[:50]}...")
    
    # Step 4: Send signed request
    print("\n📍 Step 4: Send Signed Request to MCP Wrapper")
    response = requests.post(
        "http://localhost:5001/v1/tools/list",
        json=payload,
        headers={
            "X-Amorce-Agent-ID": identity.agent_id,
            "X-Agent-Signature": signature,
            "Content-Type": "application/json"
        }
    )
    
    print(f"   Response Status: {response.status_code}")
    
    if response.status_code == 200:
        print(f"   ✅ Wrapper accepted signed request!")
        tools = response.json().get('tools', [])
        print(f"   Found {len(tools)} tools:")
        for tool in tools[:5]:
            hitl = "🔒" if tool.get('requires_approval') else "✓"
            print(f"      {hitl} {tool['name']}")
    else:
        print(f"   ❌ Request failed: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        return False
    
    # Step 5: Execute a tool (list_directory - no HITL)
    print("\n📍 Step 5: Execute Tool with Signed Request")
    
    tool_payload = {
        "payload": {
            "tool_name": "list_directory",
            "arguments": {"path": "/private/tmp"}
        }
    }
    
    tool_payload_json = json.dumps(tool_payload, sort_keys=True)
    tool_signature = identity.sign_data(tool_payload_json.encode('utf-8'))
    
    response = requests.post(
        "http://localhost:5001/v1/tools/call",
        json=tool_payload,
        headers={
            "X-Amorce-Agent-ID": identity.agent_id,
            "X-Agent-Signature": tool_signature,
            "Content-Type": "application/json"
        }
    )
    
    print(f"   Response Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"   ✅ Tool executed successfully!")
        print(f"   Status: {result.get('status')}")
        print(f"   Tool: {result.get('tool_name')}")
        print(f"   Result type: {type(result.get('result'))}")
    else:
        print(f"   ❌ Tool execution failed: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        return False
    
    # Summary
    print("\n" + "="*70)
    print("✅ PHASE 3 COMPLETE: SIGNED REQUESTS WORKING")
    print("="*70)
    print("\n✅ Verified:")
    print("   - Unsigned requests rejected (401)")
    print("   - Signed requests accepted (200)")
    print("   - Tool discovery works with signatures")
    print("   - Tool execution works with signatures")
    print("   - Complete: Agent → MCP Wrapper → MCP Server → Response")
    
    return True


if __name__ == "__main__":
    result = test_signed_request_to_wrapper()
    sys.exit(0 if result else 1)

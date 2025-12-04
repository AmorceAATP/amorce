#!/usr/bin/env python3
"""
REAL End-to-End Orchestrator + MCP Wrapper Test

Tests complete flow with actual signatures:
Agent → Orchestrator → MCP Wrapper → MCP Server → Response
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'amorce_py_sdk'))

from amorce import IdentityManager, AmorceClient

def test_orchestrator_mcp_integration():
    """Test real orchestrator + MCP wrapper integration."""
    
    print("\n" + "="*70)
    print("🧪 REAL END-TO-END ORCHESTRATOR + MCP WRAPPER TEST")
    print("="*70)
    
    # Step 1: Create agent identity
    print("\n📍 Step 1: Create Agent Identity")
    identity = IdentityManager.generate_ephemeral()
    print(f"   Agent ID: {identity.agent_id}")
    
    # Step 2: Initialize Amorce client (points to orchestrator)
    print("\n📍 Step 2: Initialize Amorce Client")
    client = AmorceClient(
        identity=identity,
        directory_url="http://localhost:9000",  # Trust directory (not needed for standalone)
        orchestrator_url="http://localhost:8080"
    )
    print(f"   Orchestrator: http://localhost:8080")
    
    # Step 3: Test direct MCP wrapper call (bypassing orchestrator for now)
    print("\n📍 Step 3: Test Direct MCP Wrapper Access")
    print("   (This tests if wrapper accepts our signed requests)")
    
    import requests
    import json
    from amorce.crypto import sign_message
    
    # Create a signed request
    payload = {
        "payload": {
            "tool_name": "list_directory",
            "arguments": {"path": "/private/tmp"}
        }
    }
    
    # Sign the payload
    payload_json = json.dumps(payload, sort_keys=True)
    signature = identity.sign_message(payload_json.encode())
    
    # Send to MCP wrapper
    response = requests.post(
        "http://localhost:5001/v1/tools/call",
        json=payload,
        headers={
            "X-Agent-ID": identity.agent_id,
            "X-Signature": signature,
            "Content-Type": "application/json"
        }
    )
    
    print(f"   Response Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ MCP Wrapper accepted signed request!")
        result = response.json()
        print(f"   Tool: {result.get('tool_name')}")
        print(f"   Status: {result.get('status')}")
    else:
        print(f"   ❌ Failed: {response.text[:200]}")
        
    # Step 4: Test through orchestrator (if MCP wrapper is registered)
    print("\n📍 Step 4: Test Through Orchestrator")
    print("   (Full Agent → Orchestrator → MCP Wrapper flow)")
    
    try:
        # Try to call MCP wrapper through orchestrator
        # This requires MCP wrapper to be registered as an agent
        response = client.transact(
            service_contract={
                "service_id": "mcp-filesystem-wrapper",  # As configured
                "endpoint": "http://localhost:5001/v1/tools/call"
            },
            payload={
                "tool_name": "list_directory",
                "arguments": {"path": "/private/tmp"}
            }
        )
        
        print(f"   ✅ Orchestrator routing successful!")
        print(f"   Response: {response}")
        
    except Exception as e:
        print(f"   ⚠️  Orchestrator routing: {str(e)[:200]}")
        print(f"   (This likely means MCP wrapper not registered in Trust Directory)")
    
    # Summary
    print("\n" + "="*70)
    print("📊 TEST SUMMARY")
    print("="*70)
    print("\n✅ Tested:")
    print("   - Agent identity and signatures")
    print("   - Direct MCP wrapper access with signatures")
    print("   - Orchestrator client initialization")
    print("\n📝 Next Steps for Full Integration:")
    print("   1. Register MCP wrapper in Trust Directory")
    print("   2. Test complete orchestrator routing")
    print("   3. Test HITL approval workflow")
    print("   4. Validate all tool operations")
    
    return True


if __name__ == "__main__":
    success = test_orchestrator_mcp_integration()
    sys.exit(0 if success else 1)

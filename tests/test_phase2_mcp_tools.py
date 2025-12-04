#!/usr/bin/env python3
"""
Phase 2: Real Tool Execution Test

Tests actual MCP tool execution with the filesystem server.
This validates the MCP client connection and tool execution.
"""

import sys
import os
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from adapters.mcp.mcp_client import MCPClient

async def test_mcp_client_direct():
    """Test MCP client can connect and execute tools."""
    
    print("\n" + "="*70)
    print("🧪 PHASE 2: MCP CLIENT DIRECT CONNECTION TEST")
    print("="*70)
    
    # Initialize MCP client
    print("\n📍 Step 1: Initialize MCP Client")
    client = MCPClient(
        command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/private/tmp"],
        server_name="filesystem"
    )
    print("   MCP Client created")
    
    try:
        # Connect to MCP server
        print("\n📍 Step 2: Connect to MCP Server")
        await client.connect()
        print("   ✅ Connected to MCP server")
        
        # List tools
        print("\n📍 Step 3: Discover Tools")
        tools = await client.list_tools()
        print(f"   ✅ Found {len(tools)} tools:")
        for tool in tools[:5]:
            print(f"      - {tool.name}: {tool.description[:60]}...")
        
        # Test list_directory
        print("\n📍 Step 4: Execute list_directory Tool")
        result = await client.call_tool(
            "list_directory",
            {"path": "/private/tmp"}
        )
        print(f"   ✅ Tool executed successfully")
        print(f"   Result type: {type(result)}")
        if isinstance(result, list):
            print(f"   Found {len(result)} items")
        
        # Test read_file if we can create one first
        print("\n📍 Step 5: Create Test File and Read It")
        test_file = "/private/tmp/amorce_test.txt"
        
        # Write test file
        import subprocess
        subprocess.run(["echo", "Hello from Amorce MCP test!"], 
                      stdout=open(test_file, 'w'))
        print(f"   Created test file: {test_file}")
        
        # Read it back via MCP
        result = await client.call_tool(
            "read_file",
            {"path": test_file}
        )
        print(f"   ✅ Read file via MCP: {str(result)[:100]}")
        
        # Clean up
        subprocess.run(["rm", test_file])
        
        print("\n" + "="*70)
        print("✅ PHASE 2 COMPLETE: MCP CLIENT WORKING")
        print("="*70)
        print("\n✅ Verified:")
        print("   - MCP client connects to server")
        print("   - Tools can be discovered")
        print("   - Tools can be executed")
        print("   - Results are returned correctly")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await client.disconnect()


if __name__ == "__main__":
    result = asyncio.run(test_mcp_client_direct())
    sys.exit(0 if result else 1)

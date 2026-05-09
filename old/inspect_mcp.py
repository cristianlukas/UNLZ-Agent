from mcp.server.fastmcp import FastMCP
mcp = FastMCP("test")
print("\nAttributes with 'app' or 'sse':")
for attr in dir(mcp):
    if 'app' in attr or 'sse' in attr:
        print(attr)

# MongoDB MCP server (partner) — HTTP transport, private network only.
FROM node:22-slim
RUN npm install -g mongodb-mcp-server@1
ENV MDB_MCP_TRANSPORT=http \
    MDB_MCP_HTTP_HOST=0.0.0.0 \
    MDB_MCP_HTTP_PORT=3000
EXPOSE 3000
# Reads MDB_MCP_CONNECTION_STRING from the environment (a secret).
# Restrict surface: disable destructive tools we never use.
CMD ["mongodb-mcp-server", "--disabledTools", "drop-database", "drop-collection", "drop-index", "rename-collection", "export"]

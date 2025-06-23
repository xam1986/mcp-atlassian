# MCP Atlassian

Model Context Protocol (MCP) server for Atlassian (Confluence and Jira). 
This integration is designed specifically for Atlassian Server instances and does not support Atlassian Cloud.

### Resources

- `confluence://{space_key}`: Access Confluence spaces and pages
- `confluence://{space_key}/pages/{title}`: Access specific Confluence pages
- `jira://{project_key}`: Access Jira project and its issues
- `jira://{project_key}/issues/{issue_key}`: Access specific Jira issues

#### Confluence Tools

1. `confluence_search`
   - Search Confluence content using CQL
   - Inputs:
     - `query` (string): CQL query string
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of search results with page_id, title, space, url, last_modified, type, and excerpt

2. `confluence_get_page`
   - Get content of a specific Confluence page
   - Inputs:
     - `page_id` (string): Confluence page ID
     - `include_metadata` (boolean, optional): Include page metadata (default: true)
   - Returns: Page content and optional metadata

3. `confluence_get_comments`
   - Get comments for a specific Confluence page
   - Input: 
     - `page_id` (string): Confluence page ID
   - Returns: Array of comments with author, creation date, and content

#### Jira Tools

1. `jira_get_issue`
   - Get details of a specific Jira issue
   - Inputs:
     - `issue_key` (string): Jira issue key (e.g., 'PROJ-123')
     - `expand` (string, optional): Fields to expand
   - Returns: Issue details including content and metadata

2. `jira_search`
   - Search Jira issues using JQL
   - Inputs:
     - `jql` (string): JQL query string
     - `fields` (string, optional): Comma-separated fields (default: "*all")
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of matching issues with metadata

3. `jira_get_project_issues`
   - Get all issues for a specific Jira project
   - Inputs:
     - `project_key` (string): Project key
     - `limit` (number, optional): Results limit (1-50, default: 10)
   - Returns: Array of project issues with metadata

4. `create_issue`
- Get all issues for a specific Jira project
   - Inputs:
     - `project_key` (string): Project key
     - `issueType`: issue type
     - `summary`: issue summary
     - `descr`: issue description
     - `fields`: JSON data mandatory keys are issuetype, summary and project
     - `update`: JSON dataю Use it to link issues or update worklog
     - `update_history`: bool (if true then the user's project history is updated)
   - Returns: created issue
   
5. `create_issue_link`
- Get all issues for a specific Jira project
   - Inputs:
      - `linkType`: link type
      - `inwardIssue`: from issue key
      - `outwardIssue`: to issue key
      - `comment`: comment
   - Returns: 

6. `get_issue_link_types`
- Get all issues for a specific Jira project
   - Inputs:
   - Returns: a list of available issue link types, if issue linking is enabled. Each issue link type has an id, a name and a label for the outward and inward link relationship.

## Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/xam1986/mcp-atlassian.git
   cd mcp-atlassian
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run MCP server**:
   ```bash
   python run server.py
   ```

## Configuration

The MCP Atlassian integration supports using either Confluence, Jira, or both services. You only need to provide the environment variables for the service(s) you want to use.

### Usage with Cline or another agents

1. Get API tokens from personal access tokens from jira and confluence profile

2. Rename file `.env.example` to `.env` and set fields:
   - CONFLUENCE_API_TOKEN
   - CONFLUENCE_URL
   - JIRA_API_TOKEN
   - JIRA_URL

3. Add to your `cline_mcp_settings.json` with only the services you need:

For Confluence only:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "url": "http://localhost:8093/sse",
      "type": "sse",
      "env": {
        "CONFLUENCE_URL": "https://your-domain/wiki",
        "CONFLUENCE_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

For Jira only:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "url": "http://localhost:8093/sse",
      "type": "sse",
      "env": {
        "JIRA_URL": "https://your-domain/jira",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```

For both services:
```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "url": "http://localhost:8093/sse",
      "type": "sse",
      "env": {
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_API_TOKEN": "your_api_token",
        "JIRA_URL": "https://your-domain/jira",
        "JIRA_API_TOKEN": "your_api_token"
      }
    }
  }
}
```


## Security

- Never share API tokens
- Keep .env files secure and private
- See [SECURITY.md](SECURITY.md) for best practices

## License

Licensed under MIT - see [LICENSE](LICENSE) file. This is not an official Atlassian product.

---
Note: This is a fork of the [original mcp-atlassian repository](https://github.com/sooperset/mcp-atlassian).

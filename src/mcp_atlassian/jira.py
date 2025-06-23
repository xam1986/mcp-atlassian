import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Union

from atlassian import Jira
from dotenv import load_dotenv

from config import JiraConfig
from document_types import Document
from preprocessing import TextPreprocessor

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger("mcp-jira")


class JiraFetcher:
    """Handles fetching and parsing content from Jira."""

    def __init__(self):
        url = os.getenv("JIRA_URL")
        token = os.getenv("JIRA_API_TOKEN")

        if not all([url, token]):
            raise ValueError("Missing required Jira environment variables")

        self.config = JiraConfig(url=url, api_token=token)
        self.jira = Jira(
            url=self.config.url,
            token=self.config.api_token,  # API token is used as password
            cloud=False,
            verify_ssl=False
        )
        self.preprocessor = TextPreprocessor(self.config.url)

    def _clean_text(self, text: str) -> str:
        """
        Clean text content by:
        1. Processing user mentions and links
        2. Converting HTML/wiki markup to markdown
        """
        if not text:
            return ""

        return self.preprocessor.clean_jira_text(text)

    def _parse_date(self, date_str: str) -> str:
        """Parse date string to handle various ISO formats."""
        if not date_str:
            return ""

        # Handle various timezone formats
        if "+0000" in date_str:
            date_str = date_str.replace("+0000", "+00:00")
        elif "-0000" in date_str:
            date_str = date_str.replace("-0000", "+00:00")
        # Handle other timezone formats like +0900, -0500, etc.
        elif len(date_str) >= 5 and date_str[-5] in "+-" and date_str[-4:].isdigit():
            # Insert colon between hours and minutes of timezone
            date_str = date_str[:-2] + ":" + date_str[-2:]

        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Error parsing date {date_str}: {e}")
            return date_str

    def get_issue(self, issue_key: str, expand: Optional[str] = None) -> Document:
        """
        Get a single issue with all its details.

        Args:
            issue_key: The issue key (e.g. 'PROJ-123')
            expand: Optional fields to expand

        Returns:
            Document containing issue content and metadata
        """
        try:
            issue = self.jira.issue(issue_key, expand=expand)

            # Process description and comments
            description = self._clean_text(issue["fields"].get("description", ""))

            # Get comments
            comments = []
            if "comment" in issue["fields"]:
                for comment in issue["fields"]["comment"]["comments"]:
                    processed_comment = self._clean_text(comment["body"])
                    created = self._parse_date(comment["created"])
                    author = comment["author"].get("displayName", "Unknown")
                    comments.append({"body": processed_comment, "created": created, "author": author})

            # Format created date using new parser
            created_date = self._parse_date(issue["fields"]["created"])

            links = issue["fields"].get("issuelinks", [])
            issue_links = ""

            if len(links) > 0:
                # Группируем связи по type.inward
                grouped_links = defaultdict(list)
                for link in links:
                    inward_type = link.get('type', {}).get('inward', 'Unknown')
                    inward_issue = link.get('inwardIssue', {}).get('key', 'UNKNOWN')
                    grouped_links[inward_type].append(inward_issue)

                # Формируем строки в формате "inward_type: key1, key2, ..."
                formatted_links = [
                    f"{inward_type}: {', '.join(keys)}"
                    for inward_type, keys in grouped_links.items()
                ]

                # Добавляем результат к issue_links
                issue_links = issue_links + "\n" + "\n".join(formatted_links)

            # Combine content in a more structured way
            content = f"""Issue: {issue_key}
Title: {issue['fields'].get('summary', '')}
Type: {issue['fields']['issuetype']['name']}
Status: {issue['fields']['status']['name']}
Created: {created_date}

Description:
{description}

Links: 
{issue_links}

Comments:
""" + "\n".join(
                [f"{c['created']} - {c['author']}: {c['body']}" for c in comments]
            )

            # Streamlined metadata with only essential information
            metadata = {
                "key": issue_key,
                "title": issue["fields"].get("summary", ""),
                "type": issue["fields"]["issuetype"]["name"],
                "status": issue["fields"]["status"]["name"],
                "created_date": created_date,
                "priority": issue["fields"].get("priority", {}).get("name", "None"),
                "link": f"{self.config.url.rstrip('/')}/browse/{issue_key}",
            }

            return Document(page_content=content, metadata=metadata)

        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            raise

    def search_issues(
            self, jql: str, fields: str = "*all", start: int = 0, limit: int = 50, expand: Optional[str] = None
    ) -> List[Document]:
        """
        Search for issues using JQL.

        Args:
            jql: JQL query string
            fields: Comma-separated string of fields to return
            start: Starting index
            limit: Maximum results to return
            expand: Fields to expand

        Returns:
            List of Documents containing matching issues
        """
        try:
            results = self.jira.jql(jql, fields=fields, start=start, limit=limit, expand=expand)

            documents = []
            for issue in results["issues"]:
                # Get full issue details
                doc = self.get_issue(issue["key"], expand=expand)
                documents.append(doc)

            return documents

        except Exception as e:
            logger.error(f"Error searching issues with JQL {jql}: {str(e)}")
            raise

    def get_project_issues(self, project_key: str, start: int = 0, limit: int = 50) -> List[Document]:
        """
        Get all issues for a project.

        Args:
            project_key: The project key
            start: Starting index
            limit: Maximum results to return

        Returns:
            List of Documents containing project issues
        """
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)

    def create_issue(self, projectKey: str, issueType: str, summary: str, descr: str,
                     fields: Union[str, dict] = None,
                     update_history: bool = False,
                     update: Optional[dict] = None) -> Document:
        """
        Creates an issue or a sub-task from a JSON representation
        :param projectKey: project Jira key
        :param issueType: issue type
        :param summary: issue summary
        :param descr: issue description
        :param fields: JSON data
                mandatory keys are issuetype, summary and project
        :param update: JSON data
                Use it to link issues or update worklog
        :param update_history: bool (if true then the user's project history is updated)
        :return:
            example:
                fields = dict(summary='Into The Night',
                              project = dict(key='APA'),
                              issuetype = dict(name='Story')
                              )
                update = dict(issuelinks={
                    "add": {
                        "type": {
                            "name": "Child-Issue"
                            },
                        "inwardIssue": {
                            "key": "ISSUE-KEY"
                            }
                        }
                    }
                )
                create_issue(fields=fields, update=update)
        """
        try:
            logger.info(f"create_issue {projectKey}, {issueType}, {summary}")
            if fields is None:
                fields = {}

            fields['project'] = {"key": projectKey}
            fields['summary'] = summary
            fields['issuetype'] = {"name": issueType}
            fields['description'] = descr

            response = self.jira.create_issue(fields, update_history, update)

            metadata = fields

            return Document(page_content=response, metadata=metadata)

        except Exception as e:
            logger.error(f"Error creating issue with {fields}: {str(e)}")
            raise

    def create_issue_link(self, linkType: str, inwardIssue: str, outwardIssue: str, comment: str = None) -> Document:
        """
        Creates an issue link between two issues.
        :param linkType: link type
        :param inwardIssue: from issue key
        :param outwardIssue: to issue key
        :param comment: comment
        :return:
        """
        try:
            logger.info(f"create_issue_link {linkType}, {inwardIssue}, {outwardIssue}")

            data = {"type": {"name": linkType},
                    "inwardIssue": {"key": inwardIssue},
                    "outwardIssue": {"key": outwardIssue},
                    "comment": {"body": comment}}

            response = self.jira.create_issue_link(data)

            metadata = data

            return Document(page_content=response, metadata=metadata)

        except Exception as e:
            logger.error(f"Error link issue with {data}: {str(e)}")
            raise

    def get_issue_link_types(self) -> List[Document]:
        """Returns a list of available issue link types,
        if issue linking is enabled.
        Each issue link type has an id,
        a name and a label for the outward and inward link relationship.
        """
        response = self.jira.get_issue_link_types()
        return Document(page_content=response, metadata=response)

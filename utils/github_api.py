"""GitHub API utility functions for fetching repository information.

This module provides functions to interact with the GitHub REST API
to retrieve repository metadata such as stars, forks, and descriptions.
"""

import logging
import os
import time
from typing import Dict, Optional, Any
import requests


# Configure logging
logger = logging.getLogger(__name__)


def get_repo_info(
    owner: str,
    repo: str,
    github_token: Optional[str] = None,
    timeout: float = 30.0
) -> Dict[str, Any]:
    """Fetch basic repository information from GitHub API.

    This function retrieves key metadata about a GitHub repository,
    including star count, fork count, description, and other basic details.

    Args:
        owner: Repository owner's username or organization name.
        repo: Repository name.
        github_token: Optional GitHub personal access token for authenticated
            requests. If not provided, uses unauthenticated access (subject to
            stricter rate limits). The token can also be set via GITHUB_TOKEN
            environment variable.
        timeout: Request timeout in seconds.

    Returns:
        A dictionary containing repository information with keys:
            - 'name': Repository name
            - 'full_name': Full repository name (owner/repo)
            - 'description': Repository description
            - 'html_url': GitHub URL
            - 'stargazers_count': Number of stars
            - 'forks_count': Number of forks
            - 'language': Primary programming language
            - 'created_at': Creation timestamp
            - 'updated_at': Last update timestamp
            - 'pushed_at': Last push timestamp
            - 'open_issues_count': Number of open issues
            - 'license': License information if available
            - 'archived': Whether repository is archived
            - 'disabled': Whether repository is disabled

    Raises:
        requests.exceptions.RequestException: For network-related errors.
        ValueError: If the repository is not found or API returns an error.
        TimeoutError: If the request times out.

    Examples:
        >>> info = get_repo_info("octocat", "Hello-World")
        >>> print(info['stargazers_count'])
        1234
    """
    # Use token from parameter or environment variable
    token = github_token or os.environ.get("GITHUB_TOKEN")
    
    # Construct API URL
    url = f"https://api.github.com/repos/{owner}/{repo}"
    
    # Prepare headers
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Knowledge-Base/1.0"
    }
    
    # Add authorization if token is available
    if token:
        headers["Authorization"] = f"Bearer {token}"
        logger.debug("Using authenticated request with GitHub token")
    else:
        logger.warning(
            "No GitHub token provided. Using unauthenticated requests "
            "which have stricter rate limits (60 requests per hour)."
        )
    
    try:
        logger.info(f"Fetching repository info for {owner}/{repo}")
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        data = response.json()
        logger.debug(f"Successfully fetched data for {owner}/{repo}")
        
        # Extract relevant fields
        result = {
            "name": data.get("name"),
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "html_url": data.get("html_url"),
            "stargazers_count": data.get("stargazers_count", 0),
            "forks_count": data.get("forks_count", 0),
            "language": data.get("language"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "pushed_at": data.get("pushed_at"),
            "open_issues_count": data.get("open_issues_count", 0),
            "license": data.get("license", {}).get("name") if data.get("license") else None,
            "archived": data.get("archived", False),
            "disabled": data.get("disabled", False),
        }
        
        return result
        
    except requests.exceptions.Timeout as e:
        logger.error(f"Request timed out for {owner}/{repo}: {e}")
        raise TimeoutError(f"GitHub API request timed out after {timeout} seconds") from e
        
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else None
        if status_code == 404:
            logger.error(f"Repository {owner}/{repo} not found")
            raise ValueError(f"Repository {owner}/{repo} not found") from e
        elif status_code == 403:
            logger.error(f"Rate limit exceeded or access forbidden for {owner}/{repo}")
            raise ValueError("GitHub API rate limit exceeded or access forbidden") from e
        else:
            logger.error(f"HTTP error {status_code} for {owner}/{repo}: {e}")
            raise ValueError(f"GitHub API returned error: {e}") from e
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while fetching {owner}/{repo}: {e}")
        raise
        
    except (KeyError, TypeError) as e:
        logger.error(f"Unexpected response format from GitHub API for {owner}/{repo}: {e}")
        raise ValueError("GitHub API returned unexpected response format") from e


def get_repo_info_with_retry(
    owner: str,
    repo: str,
    github_token: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    timeout: float = 30.0
) -> Dict[str, Any]:
    """Fetch repository information with retry logic for transient failures.

    This function wraps get_repo_info with exponential backoff retry logic
    for handling temporary network issues or rate limit errors.

    Args:
        owner: Repository owner's username or organization name.
        repo: Repository name.
        github_token: Optional GitHub personal access token.
        max_retries: Maximum number of retry attempts.
        retry_delay: Initial delay between retries in seconds (will double
            each retry).
        timeout: Request timeout in seconds.

    Returns:
        Same as get_repo_info.

    Raises:
        Same exceptions as get_repo_info after all retries are exhausted.
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return get_repo_info(owner, repo, github_token, timeout)
            
        except (requests.exceptions.Timeout, 
                requests.exceptions.ConnectionError,
                requests.exceptions.RequestException) as e:
            last_exception = e
            
            if attempt < max_retries:
                current_delay = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1} failed for "
                    f"{owner}/{repo}. Retrying in {current_delay:.1f}s: {e}"
                )
                time.sleep(current_delay)
            else:
                logger.error(
                    f"All {max_retries + 1} attempts failed for {owner}/{repo}"
                )
                raise last_exception
                
        except (ValueError, TimeoutError) as e:
            # Don't retry on these errors (e.g., repo not found, auth errors)
            raise e


if __name__ == "__main__":
    # Example usage and simple test
    import json
    
    # Configure basic logging for example
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Test with a known repository
        info = get_repo_info("octocat", "Hello-World")
        print("Repository information:")
        print(json.dumps(info, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Error fetching repository info: {e}")
        exit(1)
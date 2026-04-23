"""Tests for GitHub API utility functions."""

import pytest
from unittest.mock import patch, Mock
from utils.github_api import get_repo_info, get_repo_info_with_retry


class TestGetRepoInfo:
    """Test cases for get_repo_info function."""
    
    @patch("utils.github_api.requests.get")
    def test_successful_request(self, mock_get):
        """Test successful API request with mock response."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Hello-World",
            "full_name": "octocat/Hello-World",
            "description": "My first repository",
            "html_url": "https://github.com/octocat/Hello-World",
            "stargazers_count": 1234,
            "forks_count": 56,
            "language": "Python",
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-01-15T00:00:00Z",
            "open_issues_count": 3,
            "license": {"name": "MIT License"},
            "archived": False,
            "disabled": False,
        }
        mock_get.return_value = mock_response
        
        # Act
        result = get_repo_info("octocat", "Hello-World")
        
        # Assert
        assert result["name"] == "Hello-World"
        assert result["full_name"] == "octocat/Hello-World"
        assert result["stargazers_count"] == 1234
        assert result["language"] == "Python"
        assert result["license"] == "MIT License"
        
    @patch("utils.github_api.requests.get")
    def test_not_found_error(self, mock_get):
        """Test 404 Not Found error handling."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        mock_get.side_effect = Exception("404 Not Found")
        
        # Act & Assert
        with pytest.raises(ValueError, match="Repository octocat/NotFound not found"):
            get_repo_info("octocat", "NotFound")
    
    @patch("utils.github_api.requests.get")
    def test_rate_limit_error(self, mock_get):
        """Test 403 Rate Limit error handling."""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response
        mock_get.side_effect = Exception("403 Forbidden")
        
        # Act & Assert
        with pytest.raises(ValueError, match="GitHub API rate limit exceeded"):
            get_repo_info("octocat", "Hello-World")
    
    @patch("utils.github_api.requests.get")
    def test_timeout_error(self, mock_get):
        """Test timeout error handling."""
        # Arrange
        mock_get.side_effect = TimeoutError("Request timed out")
        
        # Act & Assert
        with pytest.raises(TimeoutError, match="GitHub API request timed out"):
            get_repo_info("octocat", "Hello-World", timeout=0.1)


class TestGetRepoInfoWithRetry:
    """Test cases for get_repo_info_with_retry function."""
    
    @patch("utils.github_api.get_repo_info")
    def test_success_on_first_attempt(self, mock_get_repo_info):
        """Test successful retry on first attempt."""
        # Arrange
        expected_result = {"name": "test-repo"}
        mock_get_repo_info.return_value = expected_result
        
        # Act
        result = get_repo_info_with_retry("octocat", "test-repo", max_retries=3)
        
        # Assert
        assert result == expected_result
        mock_get_repo_info.assert_called_once()
    
    @patch("utils.github_api.get_repo_info")
    @patch("utils.github_api.time.sleep")
    def test_success_after_retry(self, mock_sleep, mock_get_repo_info):
        """Test successful retry after initial failure."""
        # Arrange
        expected_result = {"name": "test-repo"}
        mock_get_repo_info.side_effect = [
            Exception("Network error"),
            expected_result,
        ]
        
        # Act
        result = get_repo_info_with_retry("octocat", "test-repo", max_retries=3)
        
        # Assert
        assert result == expected_result
        assert mock_get_repo_info.call_count == 2
        mock_sleep.assert_called_once()
    
    @patch("utils.github_api.get_repo_info")
    @patch("utils.github_api.time.sleep")
    def test_failure_after_max_retries(self, mock_sleep, mock_get_repo_info):
        """Test failure after exhausting all retries."""
        # Arrange
        mock_get_repo_info.side_effect = Exception("Persistent network error")
        
        # Act & Assert
        with pytest.raises(Exception, match="Persistent network error"):
            get_repo_info_with_retry("octocat", "test-repo", max_retries=2)
        
        # Assert
        assert mock_get_repo_info.call_count == 3  # initial + 2 retries
        assert mock_sleep.call_count == 2
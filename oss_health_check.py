# pylint: disable=all

import os
import requests
import time
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta

import pypistats

from github import Github

load_dotenv()

class DockerStats:
    DOCKER_HUB_URL = "https://hub.docker.com/v2/repositories/library/{}/"

    def __init__(self, image_name):
        self.url = self.DOCKER_HUB_URL.format(image_name)

    def get_pull_count(self):
        response = requests.get(self.url)
        data = response.json()
        return data.get("pull_count")

class PypiStats:
    def __init__(self, package):
        self.package = package
        
    def get_downloads(self):
        return pypistats.recent(self.package, "week", format="json")

class GithubHealth:
    def __init__(self, repo, team_members_list = []):
        self.client_object = Github(os.environ['GITHUB_TOKEN'], per_page=100)
        self.repo = repo
        self.team_members_list = team_members_list

    @property
    def client(self):
        if self.client_object.rate_limiting[0] < 10:
            print(f"Sleeping for {self.client_object.rate_limiting_resettime - time.time():.0f} seconds to reset rate limit")
            time.sleep(self.client_object.rate_limiting_resettime - time.time())

        return self.client_object

    def external_issues_percentage(self, options=None):
        if not self.team_members_list:
            print("Note: skipping external issues % calculation as team_members_list is empty")
            return 0

        options = options or {}
        options['state'] = 'open'
        issues = self.issues_for_repo(options)

        internal_issues = [issue for issue in issues if issue.user.login.lower() in map(str.lower, self.team_members_list)]
        external_issues = [issue for issue in issues if issue not in internal_issues]

        return len(external_issues) / len(issues)

    def get_clones(self):
        return self.client_object.get_repo(self.repo).get_clones_traffic()

    def time_to_first_response_for_issues(self, options=None):
        options = options or {}
        options['state'] = 'all'
        issues = self.issues_for_repo(options)

        first_response_times = []
        for issue in issues:
            issue_comments = list(self.client.get_repo(self.repo).get_issue(issue.number).get_comments())
            if issue_comments:
                first_response_times.append(min((comment.created_at - issue.created_at).total_seconds() for comment in issue_comments))

        return sum(first_response_times) / len(first_response_times) / 86400 if first_response_times else 0

    def time_to_close_for_issues(self, options=None):
        options = options or {}
        options['state'] = 'all'
        issues = self.issues_for_repo(options)

        close_times = [(issue.closed_at - issue.created_at).total_seconds() for issue in issues if issue.closed_at]

        return sum(close_times) / len(close_times) / 86400 if close_times else 0

    def issues_closed_after_first_comment(self, options=None):
        options = options or {}
        options['state'] = 'closed'
        issues = self.issues_for_repo(options)

        closed_issues = [issue for issue in issues if issue.comments == 1]

        return len(closed_issues) / len(issues) if issues else 0

    def days_since_last_commit_of_pull_requests(self, options=None):
        options = options or {}
        options['state'] = 'open'
        pull_requests = self.pull_requests_for_repo(self.repo, options)

        days_since_last_commit = []
        for pull_request in pull_requests:
            commits = list(self.client.get_repo(self.repo).get_pull(pull_request.number).get_commits())
            if commits:
                days_since_last_commit.append(min((time.time() - commit.commit.committer.date.timestamp()) for commit in commits))

        return sum(days_since_last_commit) / len(days_since_last_commit) / 86400 if days_since_last_commit else 0

    def pull_requests_open_more_than_30_days(self, options=None):
        options = options or {}
        options['state'] = 'open'
        pull_requests = self.pull_requests_for_repo(self.repo, options)

        more_than_30_days_old = [pull_request for pull_request in pull_requests if time.time() - pull_request.created_at.timestamp() > 86400 * 30]

        return len(more_than_30_days_old) / len(pull_requests) if pull_requests else 0

    def reviewed_pull_requests_without_follow_on(self, options=None):
        options = options or {}
        options['state'] = 'all'
        pull_requests = self.pull_requests_for_repo(self.repo, options)

        no_follow_ups = 0

        for pull_request in pull_requests:
            reviews = list(self.client.get_repo(self.repo).get_pull(pull_request.number).get_reviews())
            
            if not reviews:
                no_follow_ups += 1
                continue
            else:
                last_review = reviews[-1]

                if last_review.state == 'APPROVED':
                    continue
                
                review_sent_at = last_review.submitted_at.timestamp()
                
                commits = list(self.client.get_repo(self.repo).get_pull(pull_request.number).get_commits())
                last_commit_date = commits[-1].commit.committer.date.timestamp() if commits else 0

                no_follow_ups += 1 if review_sent_at > last_commit_date else 0

        return no_follow_ups / len(pull_requests) if pull_requests else 0

    def merged_pull_requests_by_contributor(self, options=None):
        options = options or {}
        options['state'] = 'closed'
        pull_requests = self.pull_requests_for_repo(self.repo, options)

        merged_pull_requests = [pull_request for pull_request in pull_requests if pull_request.merged_at]

        merged_pull_requests_by_contributor = {}
        for pull_request in merged_pull_requests:
            contributor = pull_request.user.login
            merged_pull_requests_by_contributor[contributor] = merged_pull_requests_by_contributor.get(contributor, 0) + 1

        return merged_pull_requests_by_contributor

    def external_merged_pull_requests_percentage(self, options=None):
        if not self.team_members_list:
            print("Note: skipping external pull requests % calculation as team_members_list is empty")
            return 0

        options = options or {}
        options['state'] = 'closed'
        pull_requests = self.pull_requests_for_repo(self.repo, options)

        merged_pull_requests = [pull_request for pull_request in pull_requests if pull_request.merged_at]

        internal_pull_requests = [pull_request for pull_request in merged_pull_requests if pull_request.user.login.lower() in map(str.lower, self.team_members_list)]
        external_pull_requests = [pull_request for pull_request in merged_pull_requests if pull_request not in internal_pull_requests]

        return len(external_pull_requests) / len(pull_requests) if pull_requests else 0

    def pull_requests_for_repo(self, options=None):
        options = options or {}
        options['state'] = 'all'
        options['sort'] = 'updated'
        options['direction'] = 'desc'
        options['since'] = datetime.now() - timedelta(days=90)
        pull_requests = list(self.client.get_repo(self.repo).get_pulls(**options))
        return pull_requests

    def issues_for_repo(self, options=None):
        options = options or {}
        options['state'] = 'all'
        options['sort'] = 'updated'
        options['direction'] = 'desc'
        options['since'] = datetime.now() - timedelta(days=90)
        issues = list(self.client.get_repo(self.repo).get_issues(**options))
        return issues


if __name__ == "__main__":
    # read ai-data.json
    with open('bulk-data.json', 'r') as f:
        data = json.load(f)
        for project in data['projects']:
            print("Analyzing", project['name'])
            service = GithubHealth(project['repo'], project['team_members'])
            print(f"Average time to first response for issues: {service.time_to_first_response_for_issues()} days")
            print(f"Average time to close for issues: {service.time_to_close_for_issues()} days")
            print(f"Percentage of issues closed after first comment: {service.issues_closed_after_first_comment() * 100:.2f}%")
            print(f"Average days since last commit on open pull requests: {service.days_since_last_commit_of_pull_requests()} days")
            print(f"Percentage of pull requests open more than 30 days: {service.pull_requests_open_more_than_30_days() * 100:.2f}%")
            print(f"Percentage of reviewed pull requests without follow up: {service.reviewed_pull_requests_without_follow_on() * 100:.2f}%")
            print(f"External merged pull requests percentage: {service.external_merged_pull_requests_percentage() * 100:.2f}%")
            print(f"Merged pull requests by contributor: {service.merged_pull_requests_by_contributor()}")
            print(f"Merged pull requests by contributor: {service.merged_pull_requests_by_contributor()}")
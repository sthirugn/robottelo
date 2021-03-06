# -*- encoding: utf-8 -*-
"""Test class for Host/System Unification

Feature details: https://fedorahosted.org/katello/wiki/ContentViews


@Requirement: Contentview

@CaseAutomation: Automated

@CaseLevel: Acceptance

@CaseComponent: UI

@TestType: Functional

@CaseImportance: High

@Upstream: No
"""
import random

from fauxfactory import gen_string
from nailgun import entities, entity_mixins
from robottelo import manifests
from robottelo.api.utils import (
    enable_rhrepo_and_fetchid,
    promote,
    upload_manifest,
    get_role_by_bz,
)
from robottelo.config import settings
from robottelo.constants import (
    DEFAULT_CV,
    DEFAULT_SUBSCRIPTION_NAME,
    DISTRO_RHEL7,
    DOCKER_REGISTRY_HUB,
    DOCKER_UPSTREAM_NAME,
    ENVIRONMENT,
    FAKE_0_PUPPET_REPO,
    FAKE_0_PUPPET_MODULE,
    FAKE_0_YUM_REPO,
    FAKE_1_PUPPET_REPO,
    FAKE_1_YUM_REPO,
    FAKE_3_YUM_REPO,
    FEDORA23_OSTREE_REPO,
    FILTER_CONTENT_TYPE,
    FILTER_ERRATA_TYPE,
    FILTER_ERRATA_DATE,
    FILTER_TYPE,
    PERMISSIONS,
    PRDS,
    REPOS,
    REPOSET,
    REPO_TYPE,
    ZOO_CUSTOM_GPG_KEY,
)
from robottelo.datafactory import invalid_names_list, valid_data_list
from robottelo.decorators import (
    run_in_one_thread,
    run_only_on,
    skip_if_not_set,
    stubbed,
    tier1,
    tier2,
    tier3,
)
from robottelo.decorators.host import skip_if_os
from robottelo.helpers import read_data_file
from robottelo.test import UITestCase
from robottelo.ui.base import UIError, UINoSuchElementError
from robottelo.ui.factory import make_contentview, make_lifecycle_environment
from robottelo.ui.locators import common_locators, locators
from robottelo.ui.locators.menu import menu_locators
from robottelo.ui.locators.tab import tab_locators
from robottelo.ui.session import Session
from robottelo.vm import VirtualMachine


class ContentViewTestCase(UITestCase):
    """Implement tests for content view via UI"""

    @classmethod
    def setUpClass(cls):
        super(ContentViewTestCase, cls).setUpClass()
        cls.organization = entities.Organization().create()

    # pylint: disable=too-many-arguments
    def setup_to_create_cv(self, repo_name=None, repo_url=None, repo_type=None,
                           repo_unprotected=True, rh_repo=None, org_id=None,
                           docker_upstream_name=None):
        """Create product/repo and sync it"""

        if not rh_repo:
            repo_name = repo_name or gen_string('alpha')

            # Creates new custom product via API's
            product = entities.Product(
                organization=org_id or self.organization
            ).create()
            # Creates new custom repository via API's
            repo_id = entities.Repository(
                name=repo_name,
                url=(repo_url or FAKE_1_YUM_REPO),
                content_type=(repo_type or REPO_TYPE['yum']),
                product=product,
                unprotected=repo_unprotected,
                docker_upstream_name=docker_upstream_name,
            ).create().id
        elif rh_repo:
            # Uploads the manifest and returns the result.
            with manifests.clone() as manifest:
                upload_manifest(org_id, manifest.content)
            # Enables the RedHat repo and fetches it's Id.
            repo_id = enable_rhrepo_and_fetchid(
                basearch=rh_repo['basearch'],
                # OrgId is passed as data in API hence str
                org_id=str(org_id),
                product=rh_repo['product'],
                repo=rh_repo['name'],
                reposet=rh_repo['reposet'],
                releasever=rh_repo['releasever'],
            )
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        # Sync repository
        entities.Repository(id=repo_id).sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        return repo_id

    def _get_cv_version_environments(self, cv_version):
        """Return the list of environments promoted to the version of content
        view. The content view web page must be already opened.

        :param cv_version: The version of the current opened content view
        :type cv_version: str
        :rtype: list[str]
        """
        environment_elements = self.content_views.find_elements(
            locators.contentviews.version_environments % cv_version)
        return [env_element.text for env_element in environment_elements]

    @run_only_on('sat')
    @tier1
    def test_positive_create_with_name(self):
        """Create content views using different names

        @id: 804e51d7-f025-4ec2-a247-834afd351e89

        @assert: Content views are created
        """
        with Session(self.browser) as session:
            for name in valid_data_list():
                with self.subTest(name):
                    make_contentview(
                        session, org=self.organization.name, name=name)
                    self.assertIsNotNone(
                        self.content_views.search(name),
                        'Failed to find content view %s from %s org' % (
                            name, self.organization.name)
                    )

    @run_only_on('sat')
    @tier1
    def test_negative_create_with_invalid_name(self):
        """try to create content views using invalid names

        @id: 974f2adc-b7da-4a8c-a8b5-d231b6bda1ce

        @assert: content views are not created; proper error thrown and
        system handles it gracefully
        """
        with Session(self.browser) as session:
            # invalid_names_list is used instead of invalid_values_list
            # because save button will not be enabled if name is blank
            for name in invalid_names_list():
                with self.subTest(name):
                    make_contentview(
                        session, org=self.organization.name, name=name)
                    self.assertTrue(
                        self.content_views.wait_until_element(
                            locators['contentviews.has_error']),
                        'No validation error found for "%s" from %s org' % (
                            name, self.organization.name))
                    self.assertIsNone(self.content_views.search(name))

    @run_only_on('sat')
    @tier2
    def test_positive_end_to_end(self):
        """create content view with yum repo, publish it
        and promote it to Library +1 env

        @id: 74c1b00d-c582-434f-bf73-588532588d50

        @steps:
        1. Create Product/repo and Sync it
        2. Create CV and add created repo in step1
        3. Publish and promote it to 'Library'
        4. Promote it to next environment

        @assert: content view is created, updated with repo publish and
        promoted to next selected env

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        env_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        with Session(self.browser) as session:
            # Create Life-cycle environment
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            self.assertIsNotNone(session.nav.wait_until_element(
                locators['content_env.select_name'] % env_name))
            # Creates a CV along with product and sync'ed repository
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # Publish and promote CV to next environment
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element
                                 (common_locators['alert.success_sub_form']))
            self.content_views.promote(cv_name, 'Version 1', env_name)
            self.assertIsNotNone(self.content_views.wait_until_element
                                 (common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_add_puppet_module(self):
        """create content view with puppet repository

        @id: c772d55b-6762-4c25-bbaf-83e7c200fe8a

        @steps:
        1. Create Product/puppet repo and Sync it
        2. Create CV and add puppet modules from created repo

        @assert: content view is created, updated with puppet module

        @CaseLevel: Integration
        """
        repo_url = FAKE_0_PUPPET_REPO
        cv_name = gen_string('alpha')
        puppet_module = 'httpd'
        with Session(self.browser) as session:
            self.setup_to_create_cv(
                repo_url=repo_url, repo_type=REPO_TYPE['puppet'])
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_puppet_module(
                cv_name,
                puppet_module,
                filter_term='Latest',
            )
        # Workaround to fetch added puppet module name:
        # UI doesn't refresh and populate the added module name
        # until we logout and navigate again to puppet-module tab
        with Session(self.browser) as session:
            session.nav.go_to_select_org(self.organization.name)
            session.nav.go_to_content_views()
            module = self.content_views.fetch_puppet_module(
                cv_name, puppet_module)
            self.assertIsNotNone(module)

    @run_only_on('sat')
    @tier2
    def test_positive_remove_filter(self):
        """create empty content views filter and remove it

        @id: 6c6deae7-13f1-4638-a960-d3565d93fd64

        @assert: content views filter removed successfully

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        with Session(self.browser) as session:
            make_contentview(
                session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['exclude'],
            )
            self.content_views.remove_filter(cv_name, [filter_name])
            self.assertIsNone(self.content_views.search_filter(
                cv_name, filter_name))

    @run_only_on('sat')
    @tier2
    def test_positive_add_package_filter(self):
        """add package to content views filter

        @id: 1cc8d921-92e5-4b51-8050-a7e775095f97

        @assert: content views filter created and selected packages
        can be added for inclusion/exclusion

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['include'],
            )
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                ['cow', 'bird', 'crow', 'bear'],
                ['Equal To', 'Greater Than', 'Less Than', 'Range'],
                ['0.3', '0.5', '0.5', '4.1'],
                [None, None, None, '4.6'],
            )

    @run_only_on('sat')
    @tier2
    def test_positive_add_package_inclusion_filter_and_publish(self):
        """Add package to inclusion content views filter, publish CV and verify
        package was actually filtered

        @id: 58c32cb5-1392-478e-807a-9c023d5ca0ea

        @assert: Package is included in content view version

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        package1_name = 'cow'
        package2_name = 'bear'
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['include'],
            )
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                [package1_name],
                ['All Versions'],
                [None],
                [None],
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package1_name,
                )
            )
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package2_name,
                )
            )

    @run_only_on('sat')
    @tier2
    def test_positive_add_package_exclusion_filter_and_publish(self):
        """Add package to exclusion content views filter, publish CV and verify
        package was actually filtered

        @id: 304dfb76-a222-48ab-b6de-578a2c81210c

        @assert: Package is excluded from content view version

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        package1_name = 'cow'
        package2_name = 'bear'
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['exclude'],
            )
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                [package1_name],
                ['All Versions'],
                [None],
                [None],
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package1_name,
                )
            )
            # Verify other packages were not affected by exclusion filter
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package2_name,
                )
            )

    @run_only_on('sat')
    @tier2
    def test_positive_remove_package_from_exclusion_filter(self):
        """Remove package from content view exclusion filter

        @id: 2f0adc16-2305-4adf-8582-82e6110fa385

        @assert: Package was successfully removed from content view filter and
        is present in next published content view version

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        package_name = 'cow'
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['exclude'],
            )
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                [package_name],
                ['Equal To'],
                ['2.2-3'],
                [None],
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package_name,
                )
            )
            self.content_views.remove_packages_from_filter(
                cv_name,
                filter_name,
                [package_name],
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 2.0',
                    package_name,
                )
            )

    @run_only_on('sat')
    @tier2
    def test_positive_update_inclusive_filter_package_version(self):
        """Update version of package inside inclusive cv package filter

        @id: 8d6801de-ab82-49d6-bdeb-0f6e5c95b906

        @assert: Version was updated, next content view version contains
        package with updated version

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        package_name = 'walrus'
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['include'],
            )
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                [package_name],
                ['Equal To'],
                ['0.71-1'],
                [None],
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package_name,
                    '0.71'
                )
            )
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package_name,
                    '5.21'
                )
            )
            self.content_views.update_package_filter(
                cv_name=cv_name,
                filter_name=filter_name,
                package_name=package_name,
                version_type='Equal To',
                version_value='0.71-1',
                new_version_value='5.21-1',
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 2.0',
                    package_name,
                    '0.71'
                )
            )
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 2.0',
                    package_name,
                    '5.21'
                )
            )

    @run_only_on('sat')
    @tier2
    def test_positive_update_exclusive_filter_package_version(self):
        """Update version of package inside exclusive cv package filter

        @id: a8aa8864-190a-46c3-aeed-4953c8f3f601

        @assert: Version was updated, next content view version contains
        package with updated version

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        package_name = 'walrus'
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['exclude'],
            )
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                [package_name],
                ['Equal To'],
                ['0.71-1'],
                [None],
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package_name,
                    '0.71'
                )
            )
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    package_name,
                    '5.21'
                )
            )
            self.content_views.update_package_filter(
                cv_name=cv_name,
                filter_name=filter_name,
                package_name=package_name,
                version_type='Equal To',
                version_value='0.71-1',
                new_version_value='5.21-1',
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 2.0',
                    package_name,
                    '0.71'
                )
            )
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 2.0',
                    package_name,
                    '5.21'
                )
            )

    @run_only_on('sat')
    @tier2
    def test_positive_update_filter_affected_repos(self):
        """Update content view package filter affected repos

        @id: 8f095b11-fd63-4a23-9586-a85d6191314f

        @assert: Affected repos were updated, after new content view version
        publishing only updated repos are affected by content view filter

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo1_name = gen_string('alpha')
        repo2_name = gen_string('alpha')
        repo1_package_name = 'walrus'
        repo2_package_name = 'Walrus'
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo1_name)
            self.setup_to_create_cv(
                repo_name=repo2_name, repo_url=FAKE_3_YUM_REPO)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(
                cv_name, [repo1_name, repo2_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['include'],
            )
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                [repo1_package_name],
                ['Equal To'],
                ['0.71-1'],
                [None],
            )
            self.content_views.update_filter_affected_repos(
                cv_name,
                filter_name,
                [repo1_name],
            )
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # Verify filter affected repo1
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    repo1_package_name,
                    '0.71'
                )
            )
            self.assertIsNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    repo1_package_name,
                    '5.21'
                )
            )
            # Verify repo2 was not affected and repo2 packages are present
            self.assertIsNotNone(
                self.content_views.package_search(
                    cv_name,
                    'Version 1.0',
                    repo2_package_name,
                    '5.6.6'
                )
            )

    @run_only_on('sat')
    @tier2
    def test_negative_add_same_package_filter_twice(self):
        """Update version of package inside exclusive cv package filter

        @id: 5a97de5a-679e-4150-adf7-b4a28290b834

        @assert: Same package filter can not be added again

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        package_name = 'walrus'
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            for filter_type in FILTER_TYPE['exclude'], FILTER_TYPE['include']:
                with self.subTest(filter_type):
                    filter_name = gen_string('alpha')
                    self.content_views.add_filter(
                        cv_name,
                        filter_name,
                        FILTER_CONTENT_TYPE['package'],
                        filter_type,
                    )
                    self.content_views.add_packages_to_filter(
                        cv_name,
                        filter_name,
                        [package_name],
                        ['Equal To'],
                        ['0.71-1'],
                        [None],
                    )
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form']))
                    self.content_views.add_packages_to_filter(
                        cv_name,
                        filter_name,
                        [package_name],
                        ['Equal To'],
                        ['0.71-1'],
                        [None],
                    )
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.error_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_add_package_group_filter(self):
        """add package group to content views filter

        @id: 8c02a432-8b2a-4ba3-9613-7070b2dc2bcb

        @assert: content views filter created and selected package groups
        can be added for inclusion/exclusion

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package group'],
                FILTER_TYPE['include'],
            )
            self.content_views.add_remove_package_groups_to_filter(
                cv_name,
                filter_name,
                ['mammals']
            )
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_add_errata_filter(self):
        """add errata to content views filter

        @id: bb9eef30-62c4-435c-9573-9f31210b8d7d

        @assert: content views filter created and selected errata-id
        can be added for inclusion/exclusion

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['erratum by id'],
                FILTER_TYPE['include'],
            )
            self.content_views.add_remove_errata_to_filter(
                cv_name, filter_name, ['RHEA-2012:0001', 'RHEA-2012:0004'])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier1
    def test_positive_update_name(self):
        """Update content views name to valid one.

        @id: 7d8eb36a-536e-49dc-9eb4-a5885ec77819

        @assert: Content view is updated successfully and has proper name
        """
        name = gen_string('alpha')
        with Session(self.browser) as session:
            make_contentview(
                session,
                org=self.organization.name,
                name=name,
                description=gen_string('alpha', 15),
            )
            self.assertIsNotNone(self.content_views.search(name))
            for new_name in valid_data_list():
                with self.subTest(new_name):
                    self.content_views.update(name, new_name)
                    self.assertIsNotNone(self.content_views.search(new_name))
                    name = new_name  # for next iteration

    @run_only_on('sat')
    @tier1
    def test_negative_update_name(self):
        """Try to update content views name to invalid one.

        @id: 211c319f-802a-4407-9c16-205a82d4afca

        @assert: Content View is not updated. Appropriate error shown.
        """
        name = gen_string('alpha')
        with Session(self.browser) as session:
            make_contentview(
                session, org=self.organization.name, name=name)
            self.assertIsNotNone(self.content_views.search(name))
            # invalid_names_list is used instead of invalid_values_list
            # because save button will not be enabled if name is blank
            for new_name in invalid_names_list():
                with self.subTest(new_name):
                    self.content_views.update(name, new_name)
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.error_sub_form']))
                    self.assertIsNone(self.content_views.search(new_name))

    @run_only_on('sat')
    @tier1
    def test_positive_update_description(self):
        """Update content views description to valid one.

        @id: f5e46a3b-c317-4575-9c66-ef1da1926f66

        @assert: Content view is updated successfully and has proper
        description
        """
        name = gen_string('alpha', 8)
        desc = gen_string('alpha', 15)
        with Session(self.browser) as session:
            make_contentview(
                session,
                org=self.organization.name,
                name=name,
                description=desc,
            )
            self.assertIsNotNone(self.content_views.search(name))
            for new_desc in valid_data_list():
                with self.subTest(new_desc):
                    self.content_views.update(name, new_description=new_desc)
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier3
    def test_positive_edit_rh_custom_spin(self):
        # Variations might be:
        #   * A filter on errata date (only content that matches date
        # in filter)
        #   * A filter on severity (only content of specific errata
        # severity.
        """Edit content views for a custom rh spin.  For example,
        modify a filter

        @id: 05639074-ef6d-4c6b-8ff6-53033821e686

        @assert: edited content view save is successful and info is
        updated

        @CaseLevel: System
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators.alert.success_sub_form))
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['erratum by date and type'],
                FILTER_TYPE['exclude']
            )
            # this assertion should find/open the cv and search for our filter
            self.assertIsNotNone(
                self.content_views.search_filter(cv_name, filter_name))
            # go to the filter open it, edit it and save
            self.content_views.edit_erratum_date_range_filter(
                cv_name,
                filter_name,
                errata_types=[FILTER_ERRATA_TYPE['enhancement'],
                              FILTER_ERRATA_TYPE['bugfix']],
                date_type=FILTER_ERRATA_DATE['issued'],
                start_date='2016-01-01',
                end_date='2016-06-01',
                open_filter=True
            )
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators.alert.success_sub_form))

    @run_only_on('sat')
    @tier1
    def test_positive_delete(self):
        """Delete content views

        @id: bcea6ef0-bc25-4cc7-9c0c-3591bb8810e5

        @assert: Content view can be deleted and no longer appears in UI
        """
        with Session(self.browser) as session:
            for name in valid_data_list():
                with self.subTest(name):
                    make_contentview(
                        session, org=self.organization.name, name=name)
                    self.assertIsNotNone(
                        self.content_views.search(name),
                        'Failed to find content view %s from %s org' % (
                            name, self.organization.name)
                    )
                    self.content_views.delete(name)

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier3
    def test_positive_create_composite(self):
        # Note: puppet repos cannot/should not be used in this test
        # It shouldn't work - and that is tested in a different case.
        # Individual modules from a puppet repo, however, are a valid
        # variation.
        """create a composite content views

        @id: 550f1970-5cbd-4571-bb7b-17e97639b715

        @setup: sync multiple content source/types (RH, custom, etc.)

        @assert: Composite content views are created

        @CaseLevel: System
        """
        puppet_module = 'httpd'
        cv_name1 = gen_string('alpha')
        cv_name2 = gen_string('alpha')
        composite_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name2)
            self.assertIsNotNone(self.content_views.search(cv_name2))
            self.setup_to_create_cv(
                repo_url=FAKE_0_PUPPET_REPO,
                repo_type=REPO_TYPE['puppet'],
                org_id=org.id,
            )
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name1)
            self.assertIsNotNone(self.content_views.search(cv_name1))
            self.content_views.add_puppet_module(
                cv_name1,
                puppet_module,
                filter_term='Latest',
            )
        # Workaround to fetch added puppet module name:
        # UI doesn't refresh and populate the added module name
        # until we logout and navigate again to puppet-module tab
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            module = self.content_views.fetch_puppet_module(
                cv_name1, puppet_module)
            self.assertIsNotNone(module)
            self.content_views.publish(cv_name1)
            self.content_views.add_remove_repos(cv_name2, [rh_repo['name']])
            self.content_views.publish(cv_name2)
            self.content_views.create(composite_name, is_composite=True)
            session.nav.go_to_select_org(org.name)
            self.content_views.add_remove_cv(
                composite_name, [cv_name1, cv_name2])

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier2
    def test_positive_add_rh_content(self):
        """Add Red Hat content to a content view

        @id: c370fd79-0c0d-4685-99cb-848556c786c1

        @setup: Sync RH content

        @assert: RH Content can be seen in a view

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier2
    def test_positive_add_rh_custom_spin(self):
        # Variations might be:
        #   * A filter on errata date (only content that matches date
        # in filter)
        #   * A filter on severity (only content of specific errata
        # severity.
        """associate Red Hat content in a view

        @id: 3e6c2d8a-b62d-4ec7-8353-4a6a4cb58209

        @setup: Sync RH content

        @steps: 1. Assure filter(s) applied to associated content

        @assert: Filtered RH content only is available/can be seen in a view

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators.alert.success_sub_form))
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['erratum by date and type'],
                FILTER_TYPE['exclude']
            )
            # The last executed function will create the filter and open the
            # edit filter form.
            # will not assert the filter existence here to not exit from the
            # filter edit form.
            # will edit the filter fields immediately with open_filter=False
            self.content_views.edit_erratum_date_range_filter(
                cv_name,
                filter_name,
                errata_types=[FILTER_ERRATA_TYPE['enhancement'],
                              FILTER_ERRATA_TYPE['bugfix']],
                date_type=FILTER_ERRATA_DATE['issued'],
                start_date='2016-01-01',
                end_date='2016-06-01',
                open_filter=False
            )
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators.alert.success_sub_form))
            # this assertion should find/open the cv and search for our filter
            self.assertIsNotNone(
                 self.content_views.search_filter(cv_name, filter_name))

    @run_only_on('sat')
    @tier2
    def test_positive_add_custom_content(self):
        """associate custom content in a view

        @id: 7128fc8b-0e8c-4f00-8541-2ca2399650c8

        @setup: Sync custom content

        @assert: Custom content can be seen in a view

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_negative_add_puppet_repo_to_composite(self):
        # Again, individual modules should be ok.
        """attempt to associate puppet repos within a composite
        content view

        @id: 283fa7da-ca40-4ce2-b3c5-da58ae01b8e7

        @assert: User cannot create a composite content view
        that contains direct puppet repos.

        @CaseLevel: Integration
        """
        composite_name = gen_string('alpha')
        with Session(self.browser) as session:
            make_contentview(
                session,
                org=self.organization.name,
                name=composite_name,
                is_composite=True
            )
            self.assertIsNotNone(self.content_views.search(composite_name))
            with self.assertRaises(UIError) as context:
                self.content_views.add_puppet_module(
                    composite_name, 'httpd', filter_term='Latest')
            self.assertEqual(
                context.exception.message,
                'Could not find tab to add puppet_modules'
            )

    @run_only_on('sat')
    @tier2
    def test_negative_add_components_to_non_composite(self):
        """attempt to associate components to a non-composite
        content view

        @id: fa3e6aea-7ee3-46a6-a5ba-248de3c20a8f

        @assert: User cannot add components to the view

        @CaseLevel: Integration
        """
        cv1_name = gen_string('alpha')
        cv2_name = gen_string('alpha')
        with Session(self.browser) as session:
            make_contentview(
                session, org=self.organization.name, name=cv1_name)
            self.assertIsNotNone(self.content_views.search(cv1_name))
            make_contentview(
                session, org=self.organization.name, name=cv2_name)
            self.assertIsNotNone(self.content_views.search(cv2_name))
            with self.assertRaises(UINoSuchElementError) as context:
                self.content_views.add_remove_cv(cv1_name, [cv2_name])
            self.assertEqual(
                context.exception.message,
                'Could not find ContentView tab, please make sure '
                'selected view is composite'
            )

    @run_only_on('sat')
    @tier2
    def test_negative_add_unpublished_cv_to_composite(self):
        """Attempt to associate unpublished non-composite content view with
        composite content view.

        @id: dc253606-3425-489d-bc01-266787d36841

        @steps:

        1. Create an empty non-composite content view. Do not publish it.
        2. Create a new composite content view

        @assert: Non-composite content view is not listed as available to be
        added to composite content view.

        @CaseLevel: Integration

        @BZ: 1367123
        """
        unpublished_cv_name = gen_string('alpha')
        composite_cv_name = gen_string('alpha')
        with Session(self.browser) as session:
            # Create unpublished component CV
            make_contentview(
                session, org=self.organization.name, name=unpublished_cv_name)
            self.assertIsNotNone(
                self.content_views.search(unpublished_cv_name))
            # Create composite CV
            make_contentview(
                session,
                org=self.organization.name,
                name=composite_cv_name,
                is_composite=True
            )
            self.assertIsNotNone(self.content_views.search(composite_cv_name))
            # Add component to composite CV
            with self.assertRaises(UINoSuchElementError):
                self.content_views.add_remove_cv(
                    composite_cv_name, [unpublished_cv_name])

    @run_only_on('sat')
    @tier2
    def test_negative_add_non_composite_cv_to_composite(self):
        """Attempt to associate both published and unpublished
        non-composite content views with composite content view.

        @id: 93307c2a-a03f-44fa-972d-43f6e40b9de6

        @steps:

        1. Create an empty non-composite content view. Do not publish it
        2. Create a second non-composite content view. Publish it.
        3. Create a new composite content view.
        4. Add the published non-composite content view to the composite
            content view.

        @assert:

        1. Unpublished non-composite content view is not listed as available
            to be added to composite content view.
        2. Published non-composite content view is listed as available to be
            added to composite content view.
        3. Published non-composite content view is successfully added to
            composite content view.

        @CaseLevel: Integration

        @BZ: 1367123
        """
        published_cv_name = gen_string('alpha')
        unpublished_cv_name = gen_string('alpha')
        composite_cv_name = gen_string('alpha')
        with Session(self.browser) as session:
            # Create published component CV
            make_contentview(
                session, org=self.organization.name, name=published_cv_name)
            self.assertIsNotNone(
                self.content_views.search(published_cv_name))
            self.content_views.publish(published_cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # Create unpublished component CV
            make_contentview(
                session, org=self.organization.name, name=unpublished_cv_name)
            self.assertIsNotNone(
                self.content_views.search(unpublished_cv_name))
            # Create composite CV
            make_contentview(
                session,
                org=self.organization.name,
                name=composite_cv_name,
                is_composite=True
            )
            self.assertIsNotNone(self.content_views.search(composite_cv_name))
            # Add published component to composite CV
            self.content_views.add_remove_cv(
                composite_cv_name, [published_cv_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # Add unpublished component to composite CV
            with self.assertRaises(UINoSuchElementError):
                self.content_views.add_remove_cv(
                    composite_cv_name, [unpublished_cv_name])

    @run_only_on('sat')
    @tier2
    def test_negative_add_dupe_repos(self):
        """attempt to associate the same repo multiple times within a
        content view

        @id: 24b98075-fca6-4d80-a778-066193c71e7f

        @assert: User cannot add repos multiple times to the view

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            with self.assertRaises(UIError) as context:
                self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertEqual(
                context.exception.message,
                u'Could not find repo "{0}" to add into CV'
                .format(repo_name)
            )

    @run_only_on('sat')
    @tier2
    def test_negative_add_dupe_modules(self):
        """attempt to associate duplicate puppet module(s) within a
        content view

        @id: ee33a306-9f91-439d-ac7c-d30f7e1a14cc

        @assert: User cannot add modules multiple times to the view

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        module_name = 'samba'
        product = entities.Product(organization=self.organization).create()
        puppet_repository = entities.Repository(
            url=FAKE_0_PUPPET_REPO,
            content_type='puppet',
            product=product
        ).create()
        puppet_repository.sync()
        with Session(self.browser) as session:
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_puppet_module(
                cv_name,
                module_name,
                filter_term='Latest'
            )
            # ensure that the puppet module is added to content view
            self.assertIsNotNone(
                self.content_views.fetch_puppet_module(
                    cv_name, module_name)
            )
            # ensure that cannot add the same module a second time.
            with self.assertRaises(UINoSuchElementError) as context:
                self.content_views.add_puppet_module(
                    cv_name,
                    module_name,
                    filter_term='Latest'
                )
            # ensure that the select location of our module is in the
            # exception message
            _, location = locators.contentviews.select_module % module_name
            self.assertIn(location, context.exception.message)

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier3
    def test_positive_promote_with_rh_content(self):
        """attempt to promote a content view containing RH content

        @id: 82f71639-3580-49fd-bd5a-8dba568b98d1

        @setup: Multiple environments for an org; RH content synced

        @assert: Content view can be promoted

        @CaseLevel: System
        """
        cv_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        env_name = gen_string('alpha')
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            make_lifecycle_environment(
                session, org=org.name, name=env_name)
            self.assertIsNotNone(session.nav.wait_until_element(
                (locators['content_env.select_name'] % env_name)))
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.promote(cv_name, 'Version 1', env_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier3
    def test_positive_promote_with_rh_custom_spin(self):
        """attempt to promote a content view containing a custom RH
        spin - i.e., contains filters.

        @id: 7d93c81f-2815-4b0e-b72c-23a902fe34b1

        @setup: Multiple environments for an org; RH content synced

        @assert: Content view can be promoted

        @CaseLevel: System
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        env_name = gen_string('alpha')
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            make_lifecycle_environment(
                session, org=org.name, name=env_name)
            self.assertIsNotNone(session.nav.wait_until_element(
                locators['content_env.select_name'] % env_name))
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add rh repo
            self.content_views.add_remove_repos(cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # add a filter
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['exclude'],
            )
            # assert the added filter visible
            self.assertIsNotNone(
                self.content_views.search_filter(cv_name, filter_name))
            # exclude some package in the created filter
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                ['gofer'],
                ['All Versions'],
                [None],
                [None]
            )
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.promote(cv_name, 'Version 1', env_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_promote_with_custom_content(self):
        """attempt to promote a content view containing custom content

        @id: 7c2fd8f0-c83f-4725-8953-9590112fae50

        @setup: Multiple environments for an org; custom content synced

        @assert: Content view can be promoted

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        env_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        with Session(self.browser) as session:
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            self.assertIsNotNone(
                session.nav.wait_until_element(
                    locators['content_env.select_name'] % env_name)
            )
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.promote(cv_name, 'Version 1', env_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier2
    def test_positive_promote_composite_with_custom_content(self):
        # Variations:
        # RHEL, custom content (i.e., google repos), puppet modules
        # Custom content (i.e., fedora), puppet modules
        # ...etc.
        """attempt to promote composite content view containing custom
        content

        @id: 35efbd83-d32e-4831-9d5b-1adb15289f54

        @setup: Multiple environments for an org; custom content synced

        @steps: create a composite view containing multiple content types

        @assert: Composite content view can be promoted

        @CaseLevel: Integration
        """
        env_name = gen_string('alpha')
        cv1_name = gen_string('alpha')
        cv2_name = gen_string('alpha')
        cv_composite_name = gen_string('alpha')
        custom_repo1_name = gen_string('alpha')
        custom_repo2_name = gen_string('alpha')
        custom_repo1_url = FAKE_0_YUM_REPO
        custom_repo2_url = FAKE_1_YUM_REPO
        puppet_repo1_url = FAKE_0_PUPPET_REPO
        puppet_repo2_url = FAKE_1_PUPPET_REPO
        puppet_module1 = 'httpd'
        puppet_module2 = 'ntp'
        rh7_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create a life cycle environment
            make_lifecycle_environment(
                session, org=org.name, name=env_name)
            # create repositories
            self.setup_to_create_cv(rh_repo=rh7_repo, org_id=org.id)
            self.setup_to_create_cv(
                repo_name=custom_repo1_name,
                repo_url=custom_repo1_url,
                org_id=org.id
            )
            self.setup_to_create_cv(
                repo_name=custom_repo2_name,
                repo_url=custom_repo2_url,
                org_id=org.id
            )
            self.setup_to_create_cv(
                repo_url=puppet_repo1_url,
                repo_type=REPO_TYPE['puppet'],
                org_id=org.id
            )
            self.setup_to_create_cv(
                repo_url=puppet_repo2_url,
                repo_type=REPO_TYPE['puppet'],
                org_id=org.id
            )
            # create the first content view
            make_contentview(session, org=org.name, name=cv1_name)
            self.assertIsNotNone(self.content_views.search(cv1_name))
            # add repositories to first content view
            self.content_views.add_remove_repos(
                cv1_name, [rh7_repo['name'], custom_repo1_name])
            # add the first puppet module to first content view
            self.content_views.add_puppet_module(
                cv1_name,
                puppet_module1,
                filter_term='Latest'
            )
            # publish the first content
            self.content_views.publish(cv1_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # create the second content view
            make_contentview(session, org=org.name, name=cv2_name)
            self.assertIsNotNone(self.content_views.search(cv2_name))
            # add repositories to the second content view
            self.content_views.add_remove_repos(
                cv2_name, [custom_repo2_name])
            # add the second puppet module to the second content view
            self.content_views.add_puppet_module(
                cv2_name,
                puppet_module2,
                filter_term='Latest'
            )
            # publish the second content
            self.content_views.publish(cv2_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # create a composite content view
            self.content_views.create(cv_composite_name, is_composite=True)
            self.assertIsNotNone(self.content_views.search(cv_composite_name))
            # add the first and second content views to the composite one
            self.content_views.add_remove_cv(
                cv_composite_name, [cv1_name, cv2_name])
            # publish the composite content view
            version_name = self.content_views.publish(cv_composite_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # promote the composite content view
            self.content_views.promote(
                cv_composite_name, version_name, env_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier3
    def test_positive_publish_with_rh_content(self):
        """attempt to publish a content view containing RH content

        @id: bd24dc13-b6c4-4a9b-acb2-cd6df30f436c

        @setup: RH content synced

        @assert: Content view can be published

        @CaseLevel: System
        """
        cv_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier3
    def test_positive_publish_with_rh_custom_spin(self):
        """attempt to publish  a content view containing a custom RH
        spin - i.e., contains filters.

        @id: 6804f399-8f09-4c53-8f0d-8e681892e93c

        @setup: Multiple environments for an org; RH content synced

        @assert: Content view can be published

        @CaseLevel: System
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        env_name = gen_string('alpha')
        # Create new org to import manifest
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create a lifecycle environment
            make_lifecycle_environment(
                session, org=org.name, name=env_name)
            self.assertIsNotNone(session.nav.wait_until_element(
                locators['content_env.select_name'] % env_name))
            self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
            # Create content view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add rh repo
            self.content_views.add_remove_repos(cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # Add a package exclude filter
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['exclude'],
            )
            # assert the added filter visible
            self.assertIsNotNone(
                self.content_views.search_filter(cv_name, filter_name))
            # exclude some package in the created filter
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                ['gofer'],
                ['All Versions'],
                [None],
                [None]
            )
            # Publish the content view
            self.content_views.publish(cv_name)
            # Assert the content view successfully published
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_publish_with_custom_content(self):
        """attempt to publish a content view containing custom content

        @id: 66b5efc7-2e43-438e-bd80-a754814222f9

        @setup: Multiple environments for an org; custom content synced

        @assert: Content view can be published

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        env_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        with Session(self.browser) as session:
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            self.assertIsNotNone(session.nav.wait_until_element(
                locators['content_env.select_name'] % env_name))
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier2
    def test_positive_publish_composite_with_custom_content(self):
        # Variations:
        # RHEL, custom content (i.e., google repos), puppet modules
        # Custom content (i.e., fedora), puppet modules
        # ...etc.
        """attempt to publish composite content view containing custom
        content

        @id: 73947204-408e-4e2e-b87f-ba2e52ee50b6

        @setup: Multiple environments for an org; custom content synced

        @assert: Composite content view can be published

        @CaseLevel: Integration
        """
        env_name = gen_string('alpha')
        cv1_name = gen_string('alpha')
        cv2_name = gen_string('alpha')
        cv_composite_name = gen_string('alpha')
        custom_repo1_name = gen_string('alpha')
        custom_repo2_name = gen_string('alpha')
        custom_repo1_url = FAKE_0_YUM_REPO
        custom_repo2_url = FAKE_1_YUM_REPO
        puppet_repo1_url = FAKE_0_PUPPET_REPO
        puppet_repo2_url = FAKE_1_PUPPET_REPO
        puppet_module1 = 'httpd'
        puppet_module2 = 'ntp'
        rh7_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create a life cycle environment
            make_lifecycle_environment(
                session, org=org.name, name=env_name)
            # create repositories
            self.setup_to_create_cv(rh_repo=rh7_repo, org_id=org.id)
            self.setup_to_create_cv(
                repo_name=custom_repo1_name,
                repo_url=custom_repo1_url,
                org_id=org.id
            )
            self.setup_to_create_cv(
                repo_name=custom_repo2_name,
                repo_url=custom_repo2_url,
                org_id=org.id
            )
            self.setup_to_create_cv(
                repo_url=puppet_repo1_url,
                repo_type=REPO_TYPE['puppet'],
                org_id=org.id
            )
            self.setup_to_create_cv(
                repo_url=puppet_repo2_url,
                repo_type=REPO_TYPE['puppet'],
                org_id=org.id
            )
            # create the first content view
            make_contentview(session, org=org.name, name=cv1_name)
            self.assertIsNotNone(self.content_views.search(cv1_name))
            # add repositories to first content view
            self.content_views.add_remove_repos(
                cv1_name, [rh7_repo['name'], custom_repo1_name])
            # add the first puppet module to first content view
            self.content_views.add_puppet_module(
                cv1_name,
                puppet_module1,
                filter_term='Latest'
            )
            # publish the first content
            cv1_version = self.content_views.publish(cv1_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # promote the first content view to environment
            self.content_views.promote(
                cv1_name, cv1_version, env_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # create the second content view
            make_contentview(session, org=org.name, name=cv2_name)
            self.assertIsNotNone(self.content_views.search(cv2_name))
            # add repositories to the second content view
            self.content_views.add_remove_repos(
                cv2_name, [custom_repo2_name])
            # add the second puppet module to the second content view
            self.content_views.add_puppet_module(
                cv2_name,
                puppet_module2,
                filter_term='Latest'
            )
            # publish the second content
            self.content_views.publish(cv2_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # create a composite content view
            self.content_views.create(cv_composite_name, is_composite=True)
            self.assertIsNotNone(self.content_views.search(cv_composite_name))
            # add the first and second content views to the composite one
            self.content_views.add_remove_cv(
                cv_composite_name, [cv1_name, cv2_name])
            # publish the composite content view
            self.content_views.publish(cv_composite_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_publish_version_changes_in_target_env(self):
        # Dev notes:
        # If Dev has version x, then when I promote version y into
        # Dev, version x goes away (ie when I promote version 1 to Dev,
        # version 3 goes away)
        """when publishing new version to environment, version
        gets updated

        @id: c9fa3def-baa2-497f-b6a6-f3b2d72d1ce9

        @setup: Multiple environments for an org; multiple versions
        of a content view created/published

        @steps:
        1. publish a view to an environment noting the CV version
        2. edit and republish a new version of a CV

        @assert: Content view version is updated in target environment.

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        env_name = gen_string('alpha')
        # will promote environment to 3 versions
        versions_count = 3
        with Session(self.browser) as session:
            # create environment lifecycle
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            self.assertIsNotNone(session.nav.wait_until_element(
                locators.content_env.select_name % env_name))
            # create content view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # begin publishing content view and promoting environment over all
            # the defined versions
            for _ in range(versions_count):
                # before each content view publishing add a new repository
                repo_name = gen_string('alpha')
                # create a repository
                self.setup_to_create_cv(repo_name=repo_name)
                # add the repository to the created content view
                self.content_views.add_remove_repos(cv_name, [repo_name])
                self.assertIsNotNone(
                    self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form'])
                )
                # publish the content view
                version_name = self.content_views.publish(cv_name)
                # assert the content view successfully published
                self.assertIsNotNone(self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form']))
                # find this version environments
                environments = self._get_cv_version_environments(
                    version_name)
                # assert that Library is in environments of this version
                self.assertIn(ENVIRONMENT, environments)
                # assert that env_name is not in environments of this version
                self.assertNotIn(env_name, environments)
                # promote content view environment to this version
                self.content_views.promote(cv_name, version_name, env_name)
                self.assertIsNotNone(self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form']))
                # find this version environments
                environments = self._get_cv_version_environments(
                    version_name)
                # assert that Library is still in environments of this version
                self.assertIn(ENVIRONMENT, environments)
                # assert that env_name is in environments of this version
                self.assertIn(env_name, environments)

    @run_only_on('sat')
    @tier2
    def test_positive_publish_version_changes_in_source_env(self):
        # Dev notes:
        # Similarly when I publish version y, version x goes away from
        # Library (ie when I publish version 2, version 1 disappears)
        """when publishing new version to environment, version
        gets updated

        @id: 576ac8b4-7efe-4267-a672-868a5f3eb28a

        @setup: Multiple environments for an org; multiple versions
        of a content view created/published

        @steps:
        1. publish a view to an environment
        2. edit and republish a new version of a CV

        @assert: Content view version is updated in source environment.

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        env_name = gen_string('alpha')
        # will promote environment to 3 versions
        versions_count = 3
        with Session(self.browser) as session:
            # create environment lifecycle
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            self.assertIsNotNone(session.nav.wait_until_element(
                locators.content_env.select_name % env_name))
            # create content view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # for the moment has no source/precedent version
            precedent_version_name = None
            # begin publishing content view and promoting environment over all
            # the defined versions
            for _ in range(versions_count):
                repo_name = gen_string('alpha')
                # create a repository
                self.setup_to_create_cv(repo_name=repo_name)
                # add the repository to the created content view
                self.content_views.add_remove_repos(cv_name, [repo_name])
                self.assertIsNotNone(
                    self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form'])
                )
                # publish the content view
                current_version_name = self.content_views.publish(cv_name)
                # assert the content view successfully published
                self.assertIsNotNone(self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form']))
                # promote env_name to the current content view version
                self.content_views.promote(cv_name, current_version_name,
                                           env_name)
                # assert env_name successfully promoted
                self.assertIsNotNone(self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form']))
                # find this content view version environments
                current_version_envs = self._get_cv_version_environments(
                    current_version_name)
                # assert that Library is in environments of this version
                self.assertIn(ENVIRONMENT, current_version_envs)
                # assert that env_name is in environments of this version
                self.assertIn(env_name, current_version_envs)
                # need to assert that the environments are not in the
                # precedent version
                if precedent_version_name:
                    # find the precedent version environments
                    precedent_version_envs = self._get_cv_version_environments(
                        precedent_version_name)
                    # assert that Library is not in environments of the
                    # precedent version
                    self.assertNotIn(ENVIRONMENT,
                                     precedent_version_envs)
                    # assert that env_name is not in the environments of the
                    # precedent version
                    self.assertNotIn(env_name, precedent_version_envs)
                # as exiting the loop, set the precedent version to this one
                # as in the nest loop will publish a new one
                precedent_version_name = current_version_name

    @run_only_on('sat')
    @tier2
    def test_positive_clone_within_same_env(self):
        """attempt to create new content view based on existing
        view within environment

        @id: 862c385b-d98c-4c29-8345-fd7a5900483a

        @assert: Content view can be cloned

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        copy_cv_name = gen_string('alpha')
        with Session(self.browser) as session:
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # Publish the CV
            self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # Copy the CV
            self.content_views.copy_view(cv_name, copy_cv_name)
            self.assertIsNotNone(self.content_views.search(copy_cv_name))
            self.assertEqual(
                repo_name,
                self.content_views.fetch_yum_content_repo_name(copy_cv_name)
            )

    @run_only_on('sat')
    @tier2
    def test_positive_clone_within_diff_env(self):
        """attempt to create new content view based on existing
        view, inside a different environment

        @id: 09b9307f-91de-4d3d-a6af-31c526ea816f

        @assert: Content view can be published

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        env_name = gen_string('alpha')
        copy_cv_name = gen_string('alpha')
        copy_env_name = gen_string('alpha')
        with Session(self.browser) as session:
            # create a repository
            self.setup_to_create_cv(repo_name=repo_name)
            # create a lifecycle environment
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            # create a content view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add repository to the created content view
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote env_name to the content view version
            self.content_views.promote(cv_name, version, env_name)
            # assert env_name successfully promoted
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # create a new lifecycle environment that we should promote to
            #  the published version of the copy of content view
            make_lifecycle_environment(
                session, org=self.organization.name, name=copy_env_name)
            # create a copy of content view with a new name
            self.content_views.copy_view(cv_name, copy_cv_name)
            # ensure that the copy of the content view exist
            self.assertIsNotNone(self.content_views.search(copy_cv_name))
            # ensure that the repository is in the copy of content view
            self.assertEqual(
                repo_name,
                self.content_views.fetch_yum_content_repo_name(copy_cv_name)
            )
            # publish the content view copy
            copy_version = self.content_views.publish(copy_cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote the other environment to the copy of content view version
            self.content_views.promote(
                copy_cv_name, copy_version, copy_env_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_not_set('fake_manifest')
    @tier2
    def test_positive_subscribe_system_with_rh_custom_spin(self):
        """Attempt to subscribe a host to content view with rh repository
         and custom filter

        @id: 3ea6719b-df4d-4b0f-b4b4-69ce852f632e

        @setup: content view with rh repo and custom spin

        @assert: Systems can be subscribed to content view(s)

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        filter_name = gen_string('alpha')
        subscription_name = DEFAULT_SUBSCRIPTION_NAME
        rh_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        # create an organization
        org = entities.Organization().create()
        # create a lifecycle environment
        env = entities.LifecycleEnvironment(organization=org).create()
        # create a repository
        self.setup_to_create_cv(org_id=org.id, rh_repo=rh_repo)
        with Session(self.browser) as session:
            # create content view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repository to content view
            self.content_views.add_remove_repos(
                cv_name, [rh_repo['name']])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # add a package exclude filter
            self.content_views.add_filter(
                cv_name,
                filter_name,
                FILTER_CONTENT_TYPE['package'],
                FILTER_TYPE['exclude'],
            )
            # assert the added filter visible
            self.assertIsNotNone(
                self.content_views.search_filter(cv_name, filter_name))
            # exclude some package in the created filter
            self.content_views.add_packages_to_filter(
                cv_name,
                filter_name,
                ['gofer'],
                ['All Versions'],
                [None],
                [None]
            )
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # promote the content view
            self.content_views.promote(cv_name, version, env.name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIn(env.name, self._get_cv_version_environments(version))
            # create an activation key
            content_view = entities.ContentView(
                    organization=org, name=cv_name).search()[0].read()
            activation_key = entities.ActivationKey(
                organization=org,
                environment=env,
                content_view=content_view
            ).create()
            # add rh subscription to activation key
            sub = entities.Subscription(organization=org)
            subscription_id = None
            for subs in sub.search():
                if subs.read_json()['product_name'] == subscription_name:
                    subscription_id = subs.id
                    break
            self.assertIsNotNone(subscription_id)
            activation_key.add_subscriptions(data={
                'quantity': 1,
                'subscription_id': subscription_id,
            })
            # create a vm host client and ensure it can be subscribed
            with VirtualMachine(distro=DISTRO_RHEL7) as host_client:
                host_client.install_katello_ca()
                result = host_client.register_contenthost(
                        org.label, activation_key.name)
                self.assertEqual(result.return_code, 0)
                # assert the host_client exists in content hosts page
                self.assertIsNotNone(
                    self.contenthost.search(host_client.hostname))

    @run_only_on('sat')
    @tier2
    def test_positive_subscribe_system_with_custom_content(self):
        """Attempt to subscribe a host to content view with custom repository

        @id: 715db997-707b-4868-b7cc-b6977fd6ac04

        @setup: content view with custom yum repo

        @assert: Systems can be subscribed to content view(s)

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        repo_url = FAKE_0_YUM_REPO
        # create an organization
        org = entities.Organization().create()
        # create a lifecycle environment
        env = entities.LifecycleEnvironment(organization=org).create()
        # create a yum repository
        self.setup_to_create_cv(
            org_id=org.id, repo_name=repo_name, repo_url=repo_url)
        with Session(self.browser) as session:
            # create content view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repository to content view
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # promote the content view
            self.content_views.promote(cv_name, version, env.name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIn(env.name, self._get_cv_version_environments(version))
            # create an activation key
            content_view = entities.ContentView(
                    organization=org, name=cv_name).search()[0].read()
            activation_key = entities.ActivationKey(
                organization=org,
                environment=env,
                content_view=content_view
            ).create()
            # create a vm host client and ensure it can be subscribed
            with VirtualMachine(distro=DISTRO_RHEL7) as host_client:
                host_client.install_katello_ca()
                result = host_client.register_contenthost(
                        org.label, activation_key.name)
                # without an rh subscription the result code is != 0
                # see issue #4153
                # so assert the system is subscribed by the message
                message = '\n'.join(result.stdout)
                self.assertIn(
                    'The system has been registered with ID:', message)
                # assert the host_client exists in content hosts page
                self.assertIsNotNone(
                    self.contenthost.search(host_client.hostname))

    @run_only_on('sat')
    @tier2
    def test_positive_subscribe_system_with_puppet_modules(self):
        """Attempt to subscribe a host to content view with puppet modules

        @id: c57fbdca-31e8-43f1-844d-b82b13c0c4de

        @setup: content view with puppet module

        @assert: Systems can be subscribed to content view(s)

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        repo_url = FAKE_0_PUPPET_REPO
        module_name = 'httpd'
        # create an organization
        org = entities.Organization().create()
        # create a lifecycle environment
        env = entities.LifecycleEnvironment(organization=org).create()
        # create repositories
        self.setup_to_create_cv(
            org_id=org.id,
            repo_url=repo_url,
            repo_name=repo_name,
            repo_type=REPO_TYPE['puppet']
        )
        with Session(self.browser) as session:
            # create content view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add puppet module to content view
            self.content_views.add_puppet_module(
                cv_name, module_name, filter_term='Latest')
            self.assertIsNotNone(
                self.content_views.fetch_puppet_module(
                    cv_name, module_name)
            )
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # promote the content view
            self.content_views.promote(cv_name, version, env.name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            self.assertIn(env.name, self._get_cv_version_environments(version))
            # create an activation key
            content_view = entities.ContentView(
                    organization=org, name=cv_name).search()[0].read()
            activation_key = entities.ActivationKey(
                organization=org,
                environment=env,
                content_view=content_view
            ).create()
            with VirtualMachine(distro=DISTRO_RHEL7) as host_client:
                host_client.install_katello_ca()
                result = host_client.register_contenthost(
                        org.label, activation_key.name)
                # without an rh subscription the result code is != 0
                # see issue #4153
                # so assert the system is subscribed by the message
                message = '\n'.join(result.stdout)
                self.assertIn(
                    'The system has been registered with ID:', message)
                # assert the host_client exists in content hosts page
                self.assertIsNotNone(
                    self.contenthost.search(host_client.hostname))

    @stubbed()
    @run_only_on('sat')
    @tier2
    def test_positive_restart_promote_via_dynflow(self):
        """attempt to restart a promotion

        @id: c7f4e673-5164-417f-a072-1cc51d176780

        @steps:
        1. (Somehow) cause a CV promotion to fail.  Not exactly sure how yet.
        2. Via Dynflow, restart promotion

        @assert: Promotion is restarted.

        @caseautomation: notautomated


        @CaseLevel: Integration
        """

    @stubbed()
    @run_only_on('sat')
    @tier2
    def test_positive_restart_publish_via_dynflow(self):
        """attempt to restart a publish

        @id: d7a1204f-5d7c-4978-bb78-f366786d006a

        @steps:
        1. (Somehow) cause a CV publish  to fail.  Not exactly sure how yet.
        2. Via Dynflow, restart publish

        @assert: Publish is restarted.

        @caseautomation: notautomated


        @CaseLevel: Integration
        """

    # ROLES TESTING
    # All this stuff is speculative at best.

    @run_only_on('sat')
    @tier2
    def test_positive_admin_user_actions(self):
        """Attempt to manage content views

        @id: c4d270fc-a3e6-4ae2-a338-41d864a5622a

        @steps:
        with global admin account:

        1. create a user with all content views permissions
        2. create lifecycle environment
        3. create 2 content views (one to delete, the other to manage)

        @setup: create a user with all content views permissions

        @assert: The user can Read, Modify, Delete, Publish, Promote the
        content views

        @CaseLevel: Integration
        """
        # note: the user to be created should not have permissions to access
        # products repositories
        repo_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        cv_new_name = gen_string('alpha')
        cv_copy_name = gen_string('alpha')
        env_name = gen_string('alpha')
        user_login = gen_string('alpha')
        user_password = gen_string('alphanumeric')
        role_name = gen_string('alpha')
        # create a role with all content views permissions
        role = entities.Role(name=role_name).create()
        entities.Filter(
            organization=[self.organization],
            permission=entities.Permission(
                resource_type='Katello::ContentView').search(),
            role=role,
            search=None
        ).create()
        # create environment permissions with read only and promote access
        # to content views
        env_permissions_entities = entities.Permission(
            resource_type='Katello::KTEnvironment').search()
        user_env_permissions = [
            'promote_or_remove_content_views_to_environments',
            'view_lifecycle_environments'
        ]
        user_env_permissions_entities = [
            entity
            for entity in env_permissions_entities
            if entity.name in user_env_permissions
        ]
        entities.Filter(
            organization=[self.organization],
            permission=user_env_permissions_entities,
            role=role,
            # allow access only to the mentioned here environments
            search='name = {0} or name = {1}'.format(ENVIRONMENT, env_name)
        ).create()
        # create a user and assign the above created role
        entities.User(
            default_organization=self.organization,
            organization=[self.organization],
            role=[role],
            login=user_login,
            password=user_password
        ).create()
        # create a content view with the main admin account
        with Session(self.browser) as session:
            # create a lifecycle environment
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            # create a repository
            self.setup_to_create_cv(repo_name=repo_name)
            # create the first content view
            make_contentview(
                session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add repository to the created content view
            self.content_views.add_remove_repos(cv_name, [repo_name])
            # create a second content view as a copy of the first one
            self.content_views.copy_view(cv_name, cv_copy_name)
            self.assertIsNotNone(self.content_views.search(cv_copy_name))
        # login as the user created above
        with Session(self.browser, user_login, user_password):
            # to ensure that the created user has only the assigned
            # permissions, check that hosts menu tab does not exist
            self.assertIsNone(
                self.content_views.wait_until_element(
                    menu_locators.menu.hosts, timeout=5)
            )
            # assert that the created user is not a global admin user
            # check administer->users page
            with self.assertRaises(UINoSuchElementError) as context:
                session.nav.go_to_users()
            # assert that the administer->users menu element was not accessible
            _, locator = menu_locators.menu.users
            self.assertIn(locator, context.exception.message)
            # assert the user can access content views via the menu
            try:
                session.nav.go_to_content_views()
            except UINoSuchElementError as err:
                if menu_locators.menu.content_views[1] in err.message:
                    self.fail(
                        'content view admin user was not able to access'
                        ' content view via menu: {0}'.format(err.message)
                    )
                else:
                    raise err
            # assert the user can view all the content views created
            # by admin user
            self.assertIsNotNone(self.content_views.search(cv_name))
            self.assertIsNotNone(self.content_views.search(cv_copy_name))
            # assert that the user can delete a content view
            try:
                self.content_views.delete(cv_copy_name)
            except UINoSuchElementError as err:
                if locators.contentviews.remove[1] in err.message:
                    self.fail(
                        'content view admin user was not able to access'
                        ' the remove button: {0}'.format(err.message)
                    )
                else:
                    raise err
            # assert that the deleted content view do not exist any more
            self.assertIsNone(self.content_views.search(cv_copy_name))
            # open the content view
            self.content_views.search_and_click(cv_name)
            # assert the user can access all the content view tabs
            tabs_locators = [
                tab_locators.contentviews.tab_versions,
                (tab_locators.contentviews.tab_content,
                 locators.contentviews.content_repo),
                (tab_locators.contentviews.tab_content,
                 locators.contentviews.content_filters),
                tab_locators.contentviews.tab_file_repositories,
                tab_locators.contentviews.tab_puppet_modules,
                tab_locators.contentviews.tab_docker_content,
                tab_locators.contentviews.tab_ostree_content,
                tab_locators.contentviews.tab_history,
                tab_locators.contentviews.tab_details,
                tab_locators.contentviews.tab_tasks
            ]
            for locator in tabs_locators:
                try:
                    if isinstance(locator, tuple):
                        for sub_locator in locator:
                            self.content_views.click(sub_locator)
                    else:
                        self.content_views.click(locator)
                except UINoSuchElementError as err:
                    self.fail(
                        'content view admin user was not able to access'
                        ' a content view tab: {0}'.format(err.message)
                    )
            # assert that user can edit the content view entity
            try:
                self.content_views.update(cv_name, cv_new_name)
            except UINoSuchElementError as err:
                if locators.contentviews.edit_name[1] in err.message:
                    self.fail(
                        'the content view admin user was not able to '
                        'click on the edit name button: {0}'.format(
                            err.message)
                    )
                elif locators.contentviews.save_name[1] in err.message:
                    self.fail(
                        'the content view admin user was not able to '
                        'click on the edit name save button: {0}'.format(
                            err.message)
                    )
                elif locators.contentviews.edit_description[1] in err.message:
                    self.fail(
                        'the content view admin user was not able to '
                        'click on the description name button: {0}'.format(
                            err.message)
                    )
                elif locators.contentviews.save_description[1] in err.message:
                    self.fail(
                        'the content view admin user was not able to click '
                        'on the description name save button: {0}'.format(
                            err.message)
                    )
                else:
                    raise err
            # assert that the content view exists with the new name
            self.assertIsNotNone(self.content_views.search(cv_new_name))
            # assert that the user can publish and promote the content view
            try:
                version = self.content_views.publish(cv_new_name)
            except UINoSuchElementError as err:
                if locators.contentviews.publish[1] in err.message:
                    self.fail(
                        'the content view admin user was not able to '
                        'click on the publish button: {0}'.format(err.message))
                else:
                    raise err
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            try:
                self.content_views.promote(cv_new_name, version, env_name)
            except UINoSuchElementError as err:
                if locators.contentviews.promote_button[1] in err.message:
                    self.fail(
                        'the content view admin user was not able to '
                        'click on the promote button: {0}'.format(err.message)
                    )
                else:
                    raise err
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_readonly_user_actions(self):
        """Attempt to view content views

        @id: ebdc37ed-7887-4f64-944c-f2f92c58a206

        @setup:

        1. create a user with the Content View read-only role
        2. create content view
        3. add a custom repository to content view

        @assert: User with read-only role for content view can view the
        repository in the content view

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        user_login = gen_string('alpha')
        user_password = gen_string('alphanumeric')
        role_name = gen_string('alpha')
        # create a role with content views read only permissions
        role = entities.Role(name=role_name).create()
        entities.Filter(
            organization=[self.organization],
            permission=entities.Permission(
                resource_type='Katello::ContentView').search(
                filters={'name': 'view_content_views'}),
            role=role,
            search=None
        ).create()
        # create read only products permissions and assign it to our role
        entities.Filter(
            organization=[self.organization],
            permission=entities.Permission(
                resource_type='Katello::Product').search(
                filters={'name': 'view_products'}),
            role=role,
            search=None
        ).create()
        # create a user and assign the above created role
        entities.User(
            default_organization=self.organization,
            organization=[self.organization],
            role=[role],
            login=user_login,
            password=user_password
        ).create()
        # create a content view with the main admin account
        with Session(self.browser) as session:
            # create a repository
            self.setup_to_create_cv(repo_name=repo_name)
            # create the first content view
            make_contentview(
                session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add repository to the created content view
            self.content_views.add_remove_repos(cv_name, [repo_name])
        # login as the user created above
        with Session(self.browser, user_login, user_password):
            # to ensure that the created user has only the assigned
            # permissions, check that hosts menu tab does not exist
            self.assertIsNone(
                self.content_views.wait_until_element(
                    menu_locators.menu.hosts, timeout=5)
            )
            # assert that the created user is not a global admin user
            # check administer->users page
            with self.assertRaises(UINoSuchElementError) as context:
                session.nav.go_to_users()
            # assert that the administer->users menu element was not accessible
            _, locator = menu_locators.menu.users
            self.assertIn(locator, context.exception.message)
            # assert the user can access content views via the menu
            try:
                session.nav.go_to_content_views()
            except UINoSuchElementError as err:
                if menu_locators.menu.content_views[1] in err.message:
                    self.fail(
                        'content view read only user was not able to access'
                        ' content view via menu: {0}'.format(err.message)
                    )
                else:
                    raise err
            # assert the user can view the content view
            cv_element = self.content_views.search(cv_name)
            self.assertIsNotNone(cv_element)
            # open the content view
            self.content_views.click(cv_element)
            # assert the user can access all the content view tabs
            tabs_locators = [
                tab_locators.contentviews.tab_versions,
                (tab_locators.contentviews.tab_content,
                 locators.contentviews.content_repo),
                (tab_locators.contentviews.tab_content,
                 locators.contentviews.content_filters),
                tab_locators.contentviews.tab_file_repositories,
                tab_locators.contentviews.tab_puppet_modules,
                tab_locators.contentviews.tab_docker_content,
                tab_locators.contentviews.tab_ostree_content,
                tab_locators.contentviews.tab_history,
                tab_locators.contentviews.tab_details,
                tab_locators.contentviews.tab_tasks
            ]
            for locator in tabs_locators:
                try:
                    if isinstance(locator, tuple):
                        for sub_locator in locator:
                            self.content_views.click(sub_locator)
                    else:
                        self.content_views.click(locator)
                except UINoSuchElementError as err:
                    self.fail(
                        'content view read only user was not able to access'
                        ' a content view tab: {0}'.format(err.message)
                    )
            # assert that the user can view the repo in content view
            self.content_views.click(tab_locators.contentviews.tab_content)
            self.content_views.click(locators.contentviews.content_repo)
            self.content_views.assign_value(
                locators.contentviews.repo_search, repo_name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                locators.contentviews.select_repo % repo_name))

    @run_only_on('sat')
    @tier2
    def test_negative_non_admin_user_actions(self):
        """Attempt to manage content views

        @id: aae6eede-b40e-4e06-a5f7-59d9251aa35d

        @setup:

        1. create a user with the Content View read-only role
        2. create content view
        3. add a custom repository to content view

        @assert: User with read only role for content view cannot Modify,
         Delete, Publish, Promote the content views

        @CaseLevel: Integration
        """
        # create a content view read only user with lifecycle environment
        # permissions: view_lifecycle_environments and
        # promote_or_remove_content_views_to_environments
        repo_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        cv_new_name = gen_string('alpha')
        env_name = gen_string('alpha')
        user_login = gen_string('alpha')
        user_password = gen_string('alphanumeric')
        role_name = gen_string('alpha')
        # create a role with content views read only permissions
        role = entities.Role(name=role_name).create()
        entities.Filter(
            organization=[self.organization],
            permission=entities.Permission(
                resource_type='Katello::ContentView').search(
                filters={'name': 'view_content_views'}),
            role=role,
            search=None
        ).create()
        # create environment permissions with read only and promote access
        # to content views
        env_permissions_entities = entities.Permission(
            resource_type='Katello::KTEnvironment').search()
        user_env_permissions = [
            'promote_or_remove_content_views_to_environments',
            'view_lifecycle_environments'
        ]
        user_env_permissions_entities = [
            entity
            for entity in env_permissions_entities
            if entity.name in user_env_permissions
        ]
        entities.Filter(
            organization=[self.organization],
            permission=user_env_permissions_entities,
            role=role,
            # allow access only to the mentioned here environments
            search='name = {0} or name = {1}'.format(ENVIRONMENT, env_name)
        ).create()
        # create a user and assign the above created role
        entities.User(
            default_organization=self.organization,
            organization=[self.organization],
            role=[role],
            login=user_login,
            password=user_password
        ).create()
        # create a content views with the main admin account
        with Session(self.browser) as session:
            # create a lifecycle environment
            make_lifecycle_environment(
                session, org=self.organization.name, name=env_name)
            # create a repository
            self.setup_to_create_cv(repo_name=repo_name)
            # create the first content view
            make_contentview(
                session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add repository to the created content view
            self.content_views.add_remove_repos(cv_name, [repo_name])
        # login as the user created above
        with Session(self.browser, user_login, user_password):
            # to ensure that the created user has only the assigned
            # permissions, check that hosts menu tab does not exist
            self.assertIsNone(
                self.content_views.wait_until_element(
                    menu_locators.menu.hosts, timeout=5)
            )
            # assert the user can view the content views
            self.assertIsNotNone(self.content_views.search(cv_name))
            # assert that the user cannot delete the content view
            with self.assertRaises(UINoSuchElementError) as context:
                self.content_views.delete(cv_name)
            # ensure that the delete locator is in the exception message
            _, locator = locators.contentviews.remove
            self.assertIn(locator, context.exception.message)
            # ensure the user cannot edit the content view
            with self.assertRaises(UINoSuchElementError) as context:
                self.content_views.update(cv_name, cv_new_name)
            # ensure that the edit locator is in the exception message
            _, locator = locators.contentviews.edit_name
            self.assertIn(locator, context.exception.message)
            # ensure that the content view still exist
            self.assertIsNotNone(self.content_views.search(cv_name))
            # ensure that the user cannot publish the content view
            with self.assertRaises(UINoSuchElementError) as context:
                self.content_views.publish(cv_new_name)
            self.assertIn(
                'element None was not found while trying to click',
                context.exception.message
            )
        # publish the content view with the main admin account
        with Session(self.browser) as session:
            # select the current organisation
            session.nav.go_to_select_org(self.organization.name)
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
        # login as the user created above and try to promote the content view
        with Session(self.browser, user_login, user_password):
            with self.assertRaises(UINoSuchElementError) as context:
                self.content_views.promote(
                    cv_name, version, env_name)
            _, locator = locators.contentviews.promote_button % version
            self.assertIn(locator, context.exception.message)

    @run_only_on('sat')
    @tier2
    def test_negative_non_readonly_user_actions(self):
        """Attempt to view content views

        @id: 9cbc661a-dbe3-4b88-af27-4cf7b9544074

        @setup: create a user with the Content View without the content views
        read role

        @assert: the user cannot access content views web resources

        @CaseLevel: Integration
        """
        env_name = gen_string('alpha')
        user_login = gen_string('alpha')
        user_password = gen_string('alphanumeric')
        role_name = gen_string('alpha')
        # create a role with all content views permissions except
        # view_content_views
        role = entities.Role(name=role_name).create()
        cv_permissions_entities = entities.Permission(
            resource_type='Katello::ContentView').search()
        user_cv_permissions = list(PERMISSIONS['Katello::ContentView'])
        user_cv_permissions.remove('view_content_views')
        user_cv_permissions_entities = [
            entity
            for entity in cv_permissions_entities
            if entity.name in user_cv_permissions
        ]
        # ensure I have some content views permissions
        self.assertGreater(len(user_cv_permissions_entities), 0)
        self.assertEqual(
            len(user_cv_permissions), len(user_cv_permissions_entities))
        entities.Filter(
            organization=[self.organization],
            permission=user_cv_permissions_entities,
            role=role,
            search=None
        ).create()
        # create environment permissions with read only and promote access
        # to content views
        env_permissions_entities = entities.Permission(
            resource_type='Katello::KTEnvironment').search()
        user_env_permissions = [
            'promote_or_remove_content_views_to_environments',
            'view_lifecycle_environments'
        ]
        user_env_permissions_entities = [
            entity
            for entity in env_permissions_entities
            if entity.name in user_env_permissions
        ]
        entities.Filter(
            organization=[self.organization],
            permission=user_env_permissions_entities,
            role=role,
            # allow access only to the mentioned here environments
            search='name = {0} or name = {1}'.format(ENVIRONMENT, env_name)
        ).create()
        # create a user and assign the above created role
        entities.User(
            default_organization=self.organization,
            organization=[self.organization],
            role=[role],
            login=user_login,
            password=user_password
        ).create()
        # login as the user created above
        with Session(self.browser, user_login, user_password) as session:
            # to ensure that the created user has only the assigned
            # permissions, check that hosts menu tab does not exist
            self.assertIsNone(
                self.content_views.wait_until_element(
                    menu_locators.menu.hosts, timeout=5)
            )
            # ensure that user cannot go to content views via application menu
            with self.assertRaises(UINoSuchElementError) as context:
                session.nav.go_to_content_views()
            _, locator = menu_locators.menu.content_views
            self.assertIn(locator, context.exception.message)
            # ensure that user cannot access content views page using browser
            # URL directly
            content_views_url = ''.join(
                [settings.server.get_url(), '/content_views'])
            self.browser.get(content_views_url)
            # ensure that we have been redirected to some other url
            self.assertNotEqual(self.browser.current_url, content_views_url)
            # assert that we were redirected to katello/403
            self.assertTrue(self.browser.current_url.endswith('katello/403'))
            # to restore from last navigation and allow the test session
            # to finish normally with logging out
            # go to root url, this will allow the session to find the
            # logout button
            self.browser.get(settings.server.get_url())

    @run_only_on('sat')
    @tier2
    def test_positive_delete_default_version(self):
        """Delete a content-view version associated to 'Library'

        @id: 6000a3f5-a8c2-49a4-ba30-d73a18d39e0a

        @Assert: Deletion was performed successfully

        @CaseLevel: Integration
        """
        key_content = read_data_file(ZOO_CUSTOM_GPG_KEY)
        org = entities.Organization().create()
        gpgkey = entities.GPGKey(
            content=key_content,
            organization=org,
        ).create()
        # Creates new product without selecting GPGkey
        product = entities.Product(organization=org).create()
        # Creates new repository with GPGKey
        repo = entities.Repository(
            url=FAKE_1_YUM_REPO,
            gpg_key=gpgkey,
            product=product,
        ).create()
        # sync repository
        repo.sync()
        # Create content view
        cv = entities.ContentView(organization=org).create()
        cv.repository = [repo]
        cv = cv.update(['repository'])
        self.assertEqual(len(cv.repository), 1)
        # Publish content view
        cv.publish()
        # Get published content-view version info
        cvv = entities.ContentView(id=cv.id).read().version
        self.assertEqual(len(cvv), 1)
        # API returns version like '1.0'
        # WebUI displays version like 'Version 1.0'
        version = 'Version {0}'.format(cvv[0].read().version)
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            self.content_views.delete_version(cv.name, version)
            self.content_views.check_progress_bar_status(version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_only_on('sat')
    @tier2
    def test_positive_delete_non_default_version(self):
        """Delete a content-view version associated to non-default
        environment

        @id: 1c1beb36-e06b-419f-96db-43b4d85c5e25

        @Assert: Deletion was performed successfully

        @CaseLevel: Integration
        """
        org = entities.Organization().create()
        product = entities.Product(organization=org).create()
        repo = entities.Repository(product=product).create()
        repo.sync()
        cv = entities.ContentView(organization=org).create()
        cv.repository = [repo]
        cv.update(['repository'])
        cv.publish()

        cvv = cv.read().version[0].read()
        version = 'Version {0}'.format(cvv.version)
        lc_env = entities.LifecycleEnvironment(organization=org).create()
        cvv.promote(data={u'environment_id': lc_env.id})
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            self.content_views.delete_version(cv.name, version)
            self.content_views.check_progress_bar_status(version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_only_on('sat')
    @tier2
    def test_positive_delete_version_with_ak(self):
        """Delete a content-view version that had associated activation
        key to it

        @id: 0da50b26-f82b-4663-9372-4c39270d4323

        @Assert: Deletion was performed successfully

        @CaseLevel: Integration
        """
        org = entities.Organization().create()
        cv = entities.ContentView(organization=org).create()
        cv.publish()
        cvv = cv.read().version[0].read()
        version = 'Version {0}'.format(cvv.version)
        lc_env = entities.LifecycleEnvironment(organization=org).create()
        cvv.promote(data={u'environment_id': lc_env.id})

        ak = entities.ActivationKey(
            name=gen_string('alphanumeric'),
            environment=lc_env.id,
            organization=org,
            content_view=cv,
        ).create()

        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            session.nav.go_to_content_views()
            self.content_views.validate_version_cannot_be_deleted(
                cv.name,
                version,
            )
            self.activationkey.update(
                ak.name,
                content_view=DEFAULT_CV,
                env=ENVIRONMENT,
            )
            self.content_views.delete_version(cv.name, version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_add_custom_ostree(self):
        """Create a CV with custom ostree contents

        @id: 66626fcd-9d2b-4ff5-a596-b7754b044dbe

        @Assert: CV should be created successfully with custom ostree contents

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        self.setup_to_create_cv(
            repo_name=repo_name,
            repo_url=FEDORA23_OSTREE_REPO,
            repo_type=REPO_TYPE['ostree'],
            repo_unprotected=False
        )
        with Session(self.browser) as session:
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv_name,
                [repo_name],
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_add_rh_ostree(self):
        """Create a CV with RH ostree contents

        @id: 2c6ee15f-a058-4569-a324-aec4bba1bd17

        @Assert: CV should be created successfully with RH ostree contents

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
        with Session(self.browser) as session:
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv_name,
                [rh_repo['name']],
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_remove_custom_ostree(self):
        """Create a CV with custom ostree contents and remove the
        contents.

        @id: 0e312f20-846b-440e-9c3a-392e889c9cdd

        @Assert: Content should be removed and CV should be updated
        successfully

        @CaseLevel: Integration
        """
        repo_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        self.setup_to_create_cv(
            repo_name=repo_name,
            repo_url=FEDORA23_OSTREE_REPO,
            repo_type=REPO_TYPE['ostree'],
            repo_unprotected=False
        )
        with Session(self.browser) as session:
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv_name,
                [repo_name],
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.add_remove_repos(
                cv_name,
                [repo_name],
                add_repo=False,
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_remove_rh_ostree(self):
        """Create a CV with RH ostree contents and remove the
        contents.

        @id: 852ce474-82a7-4199-9f12-5b9ad352e036

        @Assert: Content should be removed and CV should be updated
        successfully

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        rh_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        self.setup_to_create_cv(rh_repo=rh_repo, org_id=org.id)
        with Session(self.browser) as session:
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv_name,
                [rh_repo['name']],
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.add_remove_repos(
                cv_name,
                [rh_repo['name']],
                add_repo=False,
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_create_with_custom_ostree_other_contents(self):
        """Create a CV with custom ostree contents and other custom yum, puppet
        repos.

        @id: b139eb12-d960-4a45-9e22-3a22184c5415

        @Assert: CV should be created successfully with all custom contents

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        puppet_module = 'httpd'
        prod = entities.Product(organization=self.organization).create()
        # Creates new ostree repository using api
        ostree_repo = entities.Repository(
            content_type='ostree',
            url=FEDORA23_OSTREE_REPO,
            product=prod,
            unprotected=False,
        ).create()
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        ostree_repo.sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        yum_repo = entities.Repository(
            url=FAKE_1_YUM_REPO,
            product=prod,
        ).create()
        yum_repo.sync()
        puppet_repo = entities.Repository(
            url=FAKE_0_PUPPET_REPO,
            content_type='puppet',
            product=prod,
        ).create()
        puppet_repo.sync()
        with Session(self.browser) as session:
            # Create content-view
            make_contentview(session, org=self.organization.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add ostree repository to selected CV
            self.content_views.add_remove_repos(
                cv_name,
                [ostree_repo.name],
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # Add yum repository to selected CV
            self.content_views.add_remove_repos(
                cv_name,
                [yum_repo.name],
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.add_puppet_module(
                cv_name,
                puppet_module,
                filter_term='Latest',
            )
        # Workaround to fetch added puppet module name:
        # UI doesn't refresh and populate the added module name
        # until we logout and navigate again to puppet-module tab
        with Session(self.browser) as session:
            session.nav.go_to_select_org(self.organization.name)
            module = self.content_views.fetch_puppet_module(
                cv_name, puppet_module)
            self.assertIsNotNone(module)

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_create_with_rh_ostree_other_contents(self):
        """Create a CV with RH ostree contents and other RH yum repos.

        @id: 4398f5cc-62de-4a11-996b-24a7ad30ad3a

        @Assert: CV should be created successfully with all custom contents

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        rh_ah_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        rh_st_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        with manifests.clone() as manifest:
            upload_manifest(org.id, manifest.content)
        for rh_repo in [rh_ah_repo, rh_st_repo]:
            # Enables the RedHat repo and fetches it's Id.
            repo_id = enable_rhrepo_and_fetchid(
                basearch=rh_repo['basearch'],
                # OrgId is passed as data in API hence str
                org_id=str(org.id),
                product=rh_repo['product'],
                repo=rh_repo['name'],
                reposet=rh_repo['reposet'],
                releasever=rh_repo['releasever'],
            )
            old_task_timeout = entity_mixins.TASK_TIMEOUT
            # Update timeout to 10 minutes to finish sync
            entity_mixins.TASK_TIMEOUT = 600
            # Sync repository
            entities.Repository(id=repo_id).sync()
            entity_mixins.TASK_TIMEOUT = old_task_timeout
        with Session(self.browser) as session:
            # Create content-view
            make_contentview(session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv_name,
                [rh_ah_repo['name']],
                repo_type='ostree'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.add_remove_repos(
                cv_name,
                [rh_st_repo['name']],
                repo_type='yum'
            )
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_publish_with_custom_ostree(self):
        """Create a CV with custom ostree contents and publish it.

        @id: c5e8d2ba-8cb2-47d8-b352-60972cf291e9

        @Assert: CV should be published with OStree contents

        @CaseLevel: Integration
        """
        prod = entities.Product(organization=self.organization).create()
        # Creates new ostree repository using api
        ostree_repo = entities.Repository(
            content_type='ostree',
            url=FEDORA23_OSTREE_REPO,
            product=prod,
            unprotected=False,
        ).create()
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        ostree_repo.sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        cv = entities.ContentView(organization=self.organization).create()
        with Session(self.browser) as session:
            session.nav.go_to_select_org(self.organization.name)
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv.name,
                [ostree_repo.name],
                repo_type='ostree'
            )
            self.content_views.publish(cv.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_remove_published_custom_ostree_version(self):
        """Remove published custom ostree contents version from selected CV.

        @id: 949d6ee7-330a-4423-b219-550693522c7f

        @Assert: Published version with OStree contents should be removed
        successfully.

        @CaseLevel: Integration
        """
        org = entities.Organization().create()
        prod = entities.Product(organization=org).create()
        # Creates new ostree repository using api
        ostree_repo = entities.Repository(
            content_type='ostree',
            url=FEDORA23_OSTREE_REPO,
            product=prod,
            unprotected=False,
        ).create()
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        ostree_repo.sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        cv = entities.ContentView(organization=org).create()
        cv.repository = [ostree_repo]
        cv = cv.update(['repository'])
        cv.publish()
        cv = cv.read()
        cv_info = cv.version[0].read()
        version = 'Version {0}'.format(cv_info.version)
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            self.content_views.delete_version(cv.name, version)
            self.content_views.check_progress_bar_status(version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_promote_with_custom_ostree(self):
        """Create a CV with custom ostree contents and publish, promote it
        to next environment.

        @id: 05f4ddc8-a3ad-4caf-b417-3b437b48fa47

        @Assert: CV should be promoted with custom OStree contents

        @CaseLevel: Integration
        """
        prod = entities.Product(organization=self.organization).create()
        lc_env = entities.LifecycleEnvironment(
            organization=self.organization
        ).create()
        # Creates new ostree repository using api
        ostree_repo = entities.Repository(
            content_type='ostree',
            url=FEDORA23_OSTREE_REPO,
            product=prod,
            unprotected=False,
        ).create()
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        ostree_repo.sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        cv = entities.ContentView(organization=self.organization).create()
        with Session(self.browser) as session:
            session.nav.go_to_select_org(self.organization.name)
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv.name,
                [ostree_repo.name],
                repo_type='ostree'
            )
            self.content_views.publish(cv.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.promote(cv.name, 'Version 1', lc_env.name)
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_remove_promoted_custom_ostree_contents(self):
        """Remove promoted custom ostree contents from selected environment of
        CV.

        @id: a66c8a9e-953e-41a5-aaac-9d9473a3d9fc

        @Assert: Promoted custom OStree contents should be removed successfully

        @CaseLevel: Integration
        """
        org = entities.Organization().create()
        prod = entities.Product(organization=org).create()
        # Creates new ostree repository using api
        ostree_repo = entities.Repository(
            content_type='ostree',
            url=FEDORA23_OSTREE_REPO,
            product=prod,
            unprotected=False,
        ).create()
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        ostree_repo.sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        cv = entities.ContentView(organization=org).create()
        cv.repository = [ostree_repo]
        cv = cv.update(['repository'])
        cv.publish()
        cv = cv.read()
        cv_info = cv.version[0].read()
        version = 'Version {0}'.format(cv_info.version)
        lc_env = entities.LifecycleEnvironment(organization=org).create()
        promote(cv.version[0], lc_env.id)

        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            self.content_views.delete_version(cv.name, version)
            self.content_views.check_progress_bar_status(version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_publish_promote_with_custom_ostree_and_other(self):
        """Create a CV with ostree as well as yum and puppet type contents and
        publish and promote them to next environment.

        @id: cf86f9bc-e32a-4048-b793-fe6e9447f7e4

        @Assert: CV should be published and promoted with custom OStree and all
        other contents

        @CaseLevel: Integration
        """
        puppet_module = 'httpd'
        lc_env = entities.LifecycleEnvironment(
            organization=self.organization
        ).create()
        prod = entities.Product(organization=self.organization).create()
        # Creates new ostree repository using api
        ostree_repo = entities.Repository(
            content_type='ostree',
            url=FEDORA23_OSTREE_REPO,
            product=prod,
            unprotected=False,
        ).create()
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        ostree_repo.sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        yum_repo = entities.Repository(
            url=FAKE_1_YUM_REPO,
            product=prod,
        ).create()
        yum_repo.sync()
        puppet_repo = entities.Repository(
            url=FAKE_0_PUPPET_REPO,
            content_type='puppet',
            product=prod,
        ).create()
        puppet_repo.sync()
        cv = entities.ContentView(organization=self.organization).create()
        cv.repository = [ostree_repo, yum_repo]
        cv = cv.update(['repository'])
        with Session(self.browser) as session:
            session.nav.go_to_select_org(self.organization.name)
            self.content_views.add_puppet_module(
                cv.name,
                puppet_module,
                filter_term='Latest',
            )
        # Workaround to fetch added puppet module name:
        # UI doesn't refresh and populate the added module name
        # until we logout and navigate again to puppet-module tab
        with Session(self.browser) as session:
            session.nav.go_to_select_org(self.organization.name)
            module = self.content_views.fetch_puppet_module(
                cv.name, puppet_module)
            self.assertIsNotNone(module)
            self.content_views.publish(cv.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.promote(cv.name, 'Version 1', lc_env.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_remove_published_version_of_mixed_contents(self):
        """Remove mixed(ostree, yum, puppet, docker) published content version
        from selected CV.

        @id: b4d69aff-b667-43df-ac1f-28c58c73d846

        @Assert: Published version with mixed(ostree, yum, puppet, docker)
        contents should be removed successfully.

        @CaseLevel: Integration
        """
        prod = entities.Product(organization=self.organization).create()
        # Creates new ostree repository using api
        ostree_repo = entities.Repository(
            content_type='ostree',
            url=FEDORA23_OSTREE_REPO,
            product=prod,
            unprotected=False,
        ).create()
        old_task_timeout = entity_mixins.TASK_TIMEOUT
        # Update timeout to 10 minutes to finish sync
        entity_mixins.TASK_TIMEOUT = 600
        ostree_repo.sync()
        entity_mixins.TASK_TIMEOUT = old_task_timeout
        # Create new yum repository
        yum_repo = entities.Repository(
            url=FAKE_1_YUM_REPO,
            product=prod,
        ).create()
        yum_repo.sync()
        # Create new Puppet repository
        puppet_repo = entities.Repository(
            url=FAKE_0_PUPPET_REPO,
            content_type='puppet',
            product=prod,
        ).create()
        puppet_repo.sync()
        # Create new docker repository
        docker_repo = entities.Repository(
            content_type=u'docker',
            docker_upstream_name=u'busybox',
            product=prod,
            url=DOCKER_REGISTRY_HUB,
        ).create()
        docker_repo.sync()
        cv = entities.ContentView(organization=self.organization).create()
        cv.repository = [ostree_repo, yum_repo, docker_repo]
        cv = cv.update(['repository'])
        puppet_module = random.choice(
            cv.available_puppet_modules()['results']
        )
        self.assertEqual(len(cv.read().puppet_module), 0)
        entities.ContentViewPuppetModule(
            author=puppet_module['author'],
            name=puppet_module['name'],
            content_view=cv,
        ).create()
        self.assertEqual(len(cv.read().puppet_module), 1)

        cv.publish()
        cv = cv.read()
        cv_info = cv.version[0].read()
        version = 'Version {0}'.format(cv_info.version)
        with Session(self.browser) as session:
            session.nav.go_to_select_org(self.organization.name)
            self.content_views.delete_version(cv.name, version)
            self.content_views.check_progress_bar_status(version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_publish_with_rh_ostree(self):
        """Create a CV with RH ostree contents and publish it.

        @id: 4b5f487d-9de9-4645-8d73-7272f564eb75

        @Assert: CV should be published with RH OStree contents

        @CaseLevel: Integration
        """
        rh_ah_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        self.setup_to_create_cv(rh_repo=rh_ah_repo, org_id=org.id)
        cv = entities.ContentView(organization=org).create()
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            # Add repository to selected CV
            self.content_views.add_remove_repos(
                cv.name,
                [rh_ah_repo['name']],
                repo_type='ostree'
            )
            self.content_views.publish(cv.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_remove_published_rh_ostree_version(self):
        """Remove published rh ostree contents version from selected CV.

        @id: a5767568-df3a-43c0-beb7-474c82a445d4

        @Assert: Published version with RH OStree contents should be removed
        successfully.

        @CaseLevel: Integration
        """
        rh_ah_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        repo_id = self.setup_to_create_cv(rh_repo=rh_ah_repo, org_id=org.id)
        cv = entities.ContentView(organization=org).create()
        cv.repository = [entities.Repository(id=repo_id)]
        cv = cv.update(['repository'])
        cv.publish()
        cv = cv.read()
        cv_info = cv.version[0].read()
        version = 'Version {0}'.format(cv_info.version)
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            self.content_views.delete_version(cv.name, version)
            self.content_views.check_progress_bar_status(version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_promote_with_rh_ostree(self):
        """Create a CV with RH ostree contents and publish, promote it
        to next environment.

        @id: 19b7a33f-d13e-454b-bfee-295296e78967

        @Assert: CV should be promoted with RH OStree contents

        @caseautomation: notautomated

        @CaseLevel: Integration
        """
        rh_ah_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        lc_env = entities.LifecycleEnvironment(organization=org).create()
        repo_id = self.setup_to_create_cv(rh_repo=rh_ah_repo, org_id=org.id)
        cv = entities.ContentView(organization=org).create()
        cv.repository = [entities.Repository(id=repo_id)]
        cv = cv.update(['repository'])
        cv.publish()
        cv = cv.read()
        cv_info = cv.version[0].read()
        version = 'Version {0}'.format(cv_info.version)
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            self.content_views.promote(cv.name, version, lc_env.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_remove_promoted_rh_ostree_contents(self):
        """Remove promoted rh ostree contents from selected environment of CV.

        @id: 9e49e470-8b30-4941-9868-23d9718aaad9

        @Assert: Promoted rh OStree contents should be removed successfully

        @CaseLevel: Integration
        """
        rh_ah_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        lc_env = entities.LifecycleEnvironment(organization=org).create()
        repo_id = self.setup_to_create_cv(rh_repo=rh_ah_repo, org_id=org.id)
        cv = entities.ContentView(organization=org).create()
        cv.repository = [entities.Repository(id=repo_id)]
        cv = cv.update(['repository'])
        cv.publish()
        cv = cv.read()
        cv_info = cv.version[0].read()
        version = 'Version {0}'.format(cv_info.version)
        promote(cv.version[0], lc_env.id)
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            self.content_views.delete_version(cv.name, version)
            self.content_views.check_progress_bar_status(version)
            self.content_views.validate_version_deleted(cv.name, version)

    @run_in_one_thread
    @run_only_on('sat')
    @skip_if_os('RHEL6')
    @tier2
    def test_positive_publish_promote_with_rh_ostree_and_other(self):
        """Create a CV with rh ostree as well as rh yum contents and
        publish, promote them to next environment.

        @id: f1849f6a-6ad6-432f-a70c-7d61079f482a

        @Assert: CV should be published and promoted with rh ostree and all
        other contents

        @CaseLevel: Integration
        """
        rh_ah_repo = {
            'name': REPOS['rhaht']['name'],
            'product': PRDS['rhah'],
            'reposet': REPOSET['rhaht'],
            'basearch': None,
            'releasever': None,
        }
        rh_st_repo = {
            'name': REPOS['rhst7']['name'],
            'product': PRDS['rhel'],
            'reposet': REPOSET['rhst7'],
            'basearch': 'x86_64',
            'releasever': None,
        }
        # Create new org to import manifest
        org = entities.Organization().create()
        lc_env = entities.LifecycleEnvironment(organization=org).create()
        with manifests.clone() as manifest:
            upload_manifest(org.id, manifest.content)
        for rh_repo in [rh_ah_repo, rh_st_repo]:
            # Enables the RedHat repo and fetches it's Id.
            repo_id = enable_rhrepo_and_fetchid(
                basearch=rh_repo['basearch'],
                # OrgId is passed as data in API hence str
                org_id=str(org.id),
                product=rh_repo['product'],
                repo=rh_repo['name'],
                reposet=rh_repo['reposet'],
                releasever=rh_repo['releasever'],
            )
            old_task_timeout = entity_mixins.TASK_TIMEOUT
            # Update timeout to 10 minutes to finish sync
            entity_mixins.TASK_TIMEOUT = 600
            # Sync repository
            entities.Repository(id=repo_id).sync()
            entity_mixins.TASK_TIMEOUT = old_task_timeout

        cv = entities.ContentView(organization=org).create()
        with Session(self.browser) as session:
            session.nav.go_to_select_org(org.name)
            # Add ostree repository to selected CV
            self.content_views.add_remove_repos(
                cv.name,
                [rh_ah_repo['name']],
                repo_type='ostree'
            )
            # Add RH yum repository to selected CV
            self.content_views.add_remove_repos(
                cv.name,
                [rh_st_repo['name']],
                repo_type='yum'
            )
            self.content_views.publish(cv.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.content_views.promote(cv.name, 'Version 1', lc_env.name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )

    @run_in_one_thread
    @run_only_on('sat')
    @tier2
    def test_positive_promote_CV_with_custom_user_role_and_filters(self):
        """Publish and promote cv with user with custom role and filter

        @id: a07fe3df-8645-4a0c-8c56-3f8314ae4878

        @Assert: CV should be published and promoted successfully

        @CaseLevel: Integration
        """
        myrole = get_role_by_bz(1306359)
        username = gen_string('alpha')
        user_password = gen_string('alphanumeric')
        entities.User(
            login=username,
            role=[myrole],
            password=user_password,
            organization=[self.organization],
        ).create()
        repo_name = gen_string('alpha')
        env_name = gen_string('alpha')
        cv_name = gen_string('alpha')
        with Session(self.browser, username, user_password) as session:
            # Create Life-cycle environment
            make_lifecycle_environment(session, name=env_name)
            # Creates a CV along with product and sync'ed repository
            self.setup_to_create_cv(repo_name=repo_name)
            # Create content-view
            make_contentview(session, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # Add repository to selected CV
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # Publish and promote CV to next environment
            self.content_views.publish(cv_name)
            self.assertIsNotNone(self.content_views.wait_until_element
                                 (common_locators['alert.success_sub_form']))
            self.content_views.promote(cv_name, 'Version 1', env_name)
            self.assertIsNotNone(self.content_views.wait_until_element
                                 (common_locators['alert.success_sub_form']))

    @run_only_on('sat')
    @tier2
    def test_positive_remove_cv_version_from_default_env(self):
        """Remove content view version from Library environment

        @id: 43c83c15-c883-45a7-be05-d9b26da99e3c

        @Steps:

        1. Create a content view
        2. Add a yum repo to it
        3. Publish content view
        4. remove the published version from Library environment

        @Assert: content view version is removed from Library environment

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create a yum repository
            self.setup_to_create_cv(
                repo_name=repo_name,
                repo_url=FAKE_0_YUM_REPO,
                org_id=org.id
            )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repository to the created content view
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            self.assertEqual(
                self._get_cv_version_environments(version), [ENVIRONMENT])
            # remove the content view version from Library environment
            self.content_views.remove_version_from_environments(
                cv_name, version, [ENVIRONMENT])
            self.assertEqual(self._get_cv_version_environments(version), [])

    @run_only_on('sat')
    @tier2
    def test_positive_remove_renamed_cv_version_from_default_env(self):
        """Remove version of renamed content view from Library environment

        @id: bd5ca409-f3ab-43b5-bb63-3b747aa75506

        @Steps:

        1. Create a content view
        2. Add a yum repo to the content view
        3. Publish the content view
        4. Rename the content view
        5. remove the published version from Library environment

        @Assert: content view version is removed from Library environment

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        new_cv_name = gen_string('alpha')
        repo_name = gen_string('alpha')
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create a yum repository
            self.setup_to_create_cv(
                repo_name=repo_name,
                repo_url=FAKE_0_YUM_REPO,
                org_id=org.id
            )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repository to the created content view
            self.content_views.add_remove_repos(cv_name, [repo_name])
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # rename the content view
            self.content_views.update(cv_name, new_cv_name)
            self.assertIsNone(self.content_views.search(cv_name))
            # ensure the cv exits with the new name
            cv_element = self.content_views.search(new_cv_name)
            self.assertIsNotNone(cv_element)
            # open the content view
            self.content_views.click(cv_element)
            self.assertEqual(
                self._get_cv_version_environments(version), [ENVIRONMENT])
            # remove the content view version from Library environment
            self.content_views.remove_version_from_environments(
                new_cv_name, version, [ENVIRONMENT])
            self.assertEqual(self._get_cv_version_environments(version), [])

    @run_only_on('sat')
    @tier2
    def test_positive_remove_promoted_cv_version_from_default_env(self):
        """Remove promoted content view version from Library environment

        @id: a8649444-b063-4fb4-b932-a3fae7d4021d

        @Steps:

        1. Create a content view
        2. Add a puppet module(s) to the content view
        3. Publish the content view
        4. Promote the content view version from Library -> DEV
        5. remove the content view version from Library environment

        @Assert:

        1. Content view version exist only in DEV and not in Library
        2. The puppet module(s) exists in content view version

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        env_dev_name = gen_string('alpha')
        puppet_repo_url = FAKE_0_PUPPET_REPO
        puppet_module_name = FAKE_0_PUPPET_MODULE
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create the DEV lifecycle environment
            make_lifecycle_environment(
                session, org=org.name, name=env_dev_name)
            # create a puppet repository
            self.setup_to_create_cv(
                repo_url=puppet_repo_url,
                repo_type=REPO_TYPE['puppet'],
                org_id=org.id
            )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the puppet module to the created content view
            self.content_views.add_puppet_module(
                cv_name,
                puppet_module_name,
                filter_term='Latest',
            )
            self.assertIsNotNone(
                self.content_views.fetch_puppet_module(
                    cv_name, puppet_module_name)
            )
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote the content view to DEV lifecycle environment
            self.content_views.promote(cv_name, version, env_dev_name)
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                {ENVIRONMENT, env_dev_name}
            )
            # ensure that puppet module is in content view version
            self.assertIsNotNone(
                self.content_views.puppet_module_search(cv_name, version,
                                                        puppet_module_name)
            )
            # remove the content view version from Library environment
            self.content_views.remove_version_from_environments(
                cv_name, version, [ENVIRONMENT])
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                {env_dev_name}
            )
            # ensure that puppet module still in content view version
            self.assertIsNotNone(
                self.content_views.puppet_module_search(cv_name, version,
                                                        puppet_module_name)
            )

    @run_only_on('sat')
    @tier2
    def test_positive_remove_qe_promoted_cv_version_from_default_env(self):
        """Remove QE promoted content view version from Library environment

        @id: 71ad8b72-68c4-4c98-9387-077f54ef0184

        @Steps:

        1. Create a content view
        2. Add docker repo(s) to it
        3. Publish content view
        4. Promote the content view version to multiple environments
           Library -> DEV -> QE
        5. remove the content view version from Library environment

        @Assert: Content view version exist only in DEV, QE
        and not in Library

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        env_dev_name = gen_string('alpha')
        env_qe_name = gen_string('alpha')
        docker_repo_name = gen_string('alpha')
        docker_repo_url = DOCKER_REGISTRY_HUB
        docker_upstream_name = DOCKER_UPSTREAM_NAME
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create the DEV, QE lifecycle environments
            env_prior = None
            for env_name in [env_dev_name, env_qe_name]:
                make_lifecycle_environment(
                    session, org=org.name, name=env_name, prior=env_prior)
                env_prior = env_name
            # create a docker repository
            self.setup_to_create_cv(
                repo_name=docker_repo_name,
                repo_url=docker_repo_url,
                repo_type=REPO_TYPE['docker'],
                org_id=org.id,
                docker_upstream_name=docker_upstream_name
            )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the docker repo to the created content view
            self.content_views.add_remove_repos(
                cv_name, [docker_repo_name], repo_type='docker')
            self.assertIsNotNone(self.content_views.wait_until_element(
                common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote the content view to DEV, QE lifecycle environments
            for env_name in [env_dev_name, env_qe_name]:
                self.content_views.promote(cv_name, version, env_name)
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                {ENVIRONMENT, env_dev_name, env_qe_name}
            )
            # remove the content view version from Library environment
            self.content_views.remove_version_from_environments(
                cv_name, version, [ENVIRONMENT])
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                {env_dev_name, env_qe_name}
            )

    @run_only_on('sat')
    @tier2
    def test_positive_remove_prod_promoted_cv_version_from_default_env(self):
        """Remove PROD promoted content view version from Library environment

        @id: 6a874041-43c7-4682-ba06-571e49d5bbea

        @Steps:

        1. Create a content view
        2. Add yum repositories, puppet modules, docker repositories to CV
        3. Publish content view
        4. Promote the content view version to multiple environments
           Library -> DEV -> QE -> PROD
        5. remove the content view version from Library environment

        @Assert: Content view version exist only in DEV, QE, PROD
        and not in Library

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        # create env names [DEV, QE, PROD]
        env_names = [gen_string('alpha') for _ in range(3)]
        all_env_names_set = set(env_names)
        all_env_names_set.add(ENVIRONMENT)
        puppet_repo_url = FAKE_0_PUPPET_REPO
        puppet_module_name = FAKE_0_PUPPET_MODULE
        repos = [
            dict(
                repo_name=gen_string('alpha'),
                repo_url=FAKE_0_YUM_REPO,
                repo_type=REPO_TYPE['yum'],
            ),
            dict(
                repo_name=gen_string('alpha'),
                repo_url=DOCKER_REGISTRY_HUB,
                repo_type=REPO_TYPE['docker'],
                docker_upstream_name=DOCKER_UPSTREAM_NAME
            ),
            dict(
                repo_name=gen_string('alpha'),
                repo_url=puppet_repo_url,
                repo_type=REPO_TYPE['puppet'],
            ),
        ]
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create the DEV, QE, PROD lifecycle environments
            env_prior = None
            for env_name in env_names:
                make_lifecycle_environment(
                    session, org=org.name, name=env_name, prior=env_prior)
                env_prior = env_name
            # create the repositories
            for repo in repos:
                self.setup_to_create_cv(
                    org_id=org.id,
                    **repo
                )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repos to content view
            for repo in repos:
                repo_name = repo['repo_name']
                repo_type = repo['repo_type']
                if repo_type == 'puppet':
                    self.content_views.add_puppet_module(
                        cv_name,
                        puppet_module_name,
                        filter_term='Latest',
                    )
                    self.assertIsNotNone(
                        self.content_views.fetch_puppet_module(
                            cv_name, puppet_module_name)
                    )
                else:
                    self.content_views.add_remove_repos(
                        cv_name, [repo_name], repo_type=repo_type)
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote the content view to DEV, QE, PROD lifecycle environments
            for env_name in env_names:
                self.content_views.promote(cv_name, version, env_name)
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                all_env_names_set
            )
            # remove the content view version from Library environment
            self.content_views.remove_version_from_environments(
                cv_name, version, [ENVIRONMENT])
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                set(env_names)
            )

    @run_only_on('sat')
    @tier2
    def test_positive_remove_cv_version_from_env(self):
        """Remove promoted content view version from environment

        @id: d1da23ee-a5db-4990-9572-1a0919a9fe1c

        @Steps:

        1. Create a content view
        2. Add a yum repo and a puppet module to the content view
        3. Publish the content view
        4. Promote the content view version to multiple environments
           Library -> DEV -> QE -> STAGE -> PROD
        5. remove the content view version from PROD environment
        6. Assert: content view version exists only in Library, DEV, QE, STAGE
           and not in PROD
        7. Promote again from STAGE -> PROD

        @Assert: Content view version exist in Library, DEV, QE, STAGE, PROD

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        # create env names [DEV, QE, STAGE, PROD]
        env_names = [gen_string('alpha') for _ in range(4)]
        env_dev_name, env_qe_name, env_stage_name, env_prod_name = env_names
        all_env_names_set = set(env_names)
        all_env_names_set.add(ENVIRONMENT)
        puppet_repo_url = FAKE_0_PUPPET_REPO
        puppet_module_name = FAKE_0_PUPPET_MODULE
        repos = [
            dict(
                repo_name=gen_string('alpha'),
                repo_url=FAKE_0_YUM_REPO,
                repo_type=REPO_TYPE['yum'],
            ),
            dict(
                repo_name=gen_string('alpha'),
                repo_url=puppet_repo_url,
                repo_type=REPO_TYPE['puppet'],
            ),
        ]
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create the DEV, QE, STAGE, PROD lifecycle environments
            env_prior = None
            for env_name in env_names:
                make_lifecycle_environment(
                    session, org=org.name, name=env_name, prior=env_prior)
                env_prior = env_name
            # create the repositories
            for repo in repos:
                self.setup_to_create_cv(
                    org_id=org.id,
                    **repo
                )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repos to content view
            for repo in repos:
                repo_name = repo['repo_name']
                repo_type = repo['repo_type']
                if repo_type == 'puppet':
                    self.content_views.add_puppet_module(
                        cv_name,
                        puppet_module_name,
                        filter_term='Latest',
                    )
                    self.assertIsNotNone(
                        self.content_views.fetch_puppet_module(
                            cv_name, puppet_module_name)
                    )
                else:
                    self.content_views.add_remove_repos(
                        cv_name, [repo_name], repo_type=repo_type)
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote the content view to all lifecycle environments
            for env_name in env_names:
                self.content_views.promote(cv_name, version, env_name)
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                all_env_names_set
            )
            # remove the content view version from PROD environment
            self.content_views.remove_version_from_environments(
                cv_name, version, [env_prod_name])
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                {ENVIRONMENT, env_dev_name, env_qe_name, env_stage_name}
            )
            # promote again to PROD
            self.content_views.promote(cv_name, version, env_prod_name)
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                all_env_names_set
            )

    @run_only_on('sat')
    @tier2
    def test_positive_remove_cv_version_from_multi_env(self):
        """Remove promoted content view version from multiple environment

        @id: 0d54c256-ac6d-4487-ab09-4e8dd257358e

        @Steps:

        1. Create a content view
        2. Add a yum repo and a puppet module to the content view
        3. Publish the content view
        4. Promote the content view version to multiple environments
           Library -> DEV -> QE -> STAGE -> PROD
        5. Remove content view version from QE, STAGE and PROD

        @Assert: Content view version exists only in Library, DEV

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        # create env names [DEV, QE, STAGE, PROD]
        env_names = [gen_string('alpha') for _ in range(4)]
        env_dev_name, env_qe_name, env_stage_name, env_prod_name = env_names
        all_env_names_set = set(env_names)
        all_env_names_set.add(ENVIRONMENT)
        puppet_repo_url = FAKE_0_PUPPET_REPO
        puppet_module_name = FAKE_0_PUPPET_MODULE
        repos = [
            dict(
                repo_name=gen_string('alpha'),
                repo_url=FAKE_0_YUM_REPO,
                repo_type=REPO_TYPE['yum'],
            ),
            dict(
                repo_name=gen_string('alpha'),
                repo_url=puppet_repo_url,
                repo_type=REPO_TYPE['puppet'],
            ),
        ]
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create the DEV, QE, STAGE, PROD lifecycle environments
            env_prior = None
            for env_name in env_names:
                make_lifecycle_environment(
                    session, org=org.name, name=env_name, prior=env_prior)
                env_prior = env_name
            # create the repositories
            for repo in repos:
                self.setup_to_create_cv(
                    org_id=org.id,
                    **repo
                )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repos to content view
            for repo in repos:
                repo_name = repo['repo_name']
                repo_type = repo['repo_type']
                if repo_type == 'puppet':
                    self.content_views.add_puppet_module(
                        cv_name,
                        puppet_module_name,
                        filter_term='Latest',
                    )
                    self.assertIsNotNone(
                        self.content_views.fetch_puppet_module(
                            cv_name, puppet_module_name)
                    )
                else:
                    self.content_views.add_remove_repos(
                        cv_name, [repo_name], repo_type=repo_type)
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote the content view to all lifecycle environments
            for env_name in env_names:
                self.content_views.promote(cv_name, version, env_name)
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                all_env_names_set
            )
            # remove the content view version from QE, STAGE, PROD environments
            self.content_views.remove_version_from_environments(
                cv_name, version, [env_qe_name, env_stage_name, env_prod_name])
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                {ENVIRONMENT, env_dev_name}
            )

    @run_only_on('sat')
    @tier2
    def test_positive_delete_cv_promoted_to_multi_env(self):
        """Delete published content view with version promoted to multiple
         environments

        @id: f16f2db5-7f5b-4ebb-863e-6c18ff745ce4

        @Steps:

        1. Create a content view
        2. Add a yum repo and a puppet module to the content view
        3. Publish the content view
        4. Promote the content view to multiple environment
           Library -> DEV -> QE -> STAGE -> PROD
        5. Delete the content view, this should delete the content with all
           it's published/promoted versions from all environments

        @Assert: The content view doesn't exists

        @CaseLevel: Integration
        """
        cv_name = gen_string('alpha')
        # create env names [DEV, QE, STAGE, PROD]
        env_names = [gen_string('alpha') for _ in range(4)]
        all_env_names_set = set(env_names)
        all_env_names_set.add(ENVIRONMENT)
        puppet_repo_url = FAKE_0_PUPPET_REPO
        puppet_module_name = FAKE_0_PUPPET_MODULE
        repos = [
            dict(
                repo_name=gen_string('alpha'),
                repo_url=FAKE_0_YUM_REPO,
                repo_type=REPO_TYPE['yum'],
            ),
            dict(
                repo_name=gen_string('alpha'),
                repo_url=puppet_repo_url,
                repo_type=REPO_TYPE['puppet'],
            ),
        ]
        # create a new organization
        org = entities.Organization().create()
        with Session(self.browser) as session:
            # create the DEV, QE, STAGE, PROD lifecycle environments
            env_prior = None
            for env_name in env_names:
                make_lifecycle_environment(
                    session, org=org.name, name=env_name, prior=env_prior)
                env_prior = env_name
            # create the repositories
            for repo in repos:
                self.setup_to_create_cv(
                    org_id=org.id,
                    **repo
                )
            # create a content view
            make_contentview(
                session, org=org.name, name=cv_name)
            self.assertIsNotNone(self.content_views.search(cv_name))
            # add the repos to content view
            for repo in repos:
                repo_name = repo['repo_name']
                repo_type = repo['repo_type']
                if repo_type == 'puppet':
                    self.content_views.add_puppet_module(
                        cv_name,
                        puppet_module_name,
                        filter_term='Latest',
                    )
                    self.assertIsNotNone(
                        self.content_views.fetch_puppet_module(
                            cv_name, puppet_module_name)
                    )
                else:
                    self.content_views.add_remove_repos(
                        cv_name, [repo_name], repo_type=repo_type)
                    self.assertIsNotNone(self.content_views.wait_until_element(
                        common_locators['alert.success_sub_form']))
            # publish the content view
            version = self.content_views.publish(cv_name)
            self.assertIsNotNone(
                self.content_views.wait_until_element(
                    common_locators['alert.success_sub_form'])
            )
            # promote the content view to all lifecycle environments
            for env_name in env_names:
                self.content_views.promote(cv_name, version, env_name)
            self.assertEqual(
                set(self._get_cv_version_environments(version)),
                all_env_names_set
            )
            # remove all the environments from version
            self.content_views.remove_version_from_environments(
                cv_name, version, list(all_env_names_set))
            # delete content view
            self.content_views.delete(cv_name)
            self.assertIsNone(self.content_views.search(cv_name))

    @stubbed()
    @run_only_on('sat')
    @tier3
    def test_positive_remove_cv_version_from_env_with_host_registered(self):
        """Remove promoted content view version from environment that is used
        in association of an Activation key and content-host registration.

        @id: a8ca3de1-3f79-4029-8033-00315b6b854f

        @Steps:

        1. Create a content view cv1
        2. Add a yum repo and a puppet module to the content view
        3. Publish the content view
        4. Promote the content view to multiple environment
           Library -> DEV -> QE
        5. Create an Activation key with the QE environment
        6. Register a content-host using the Activation key
        7. Remove the content view cv1 version from QE environment.
           The remove environment wizard should propose to replace the current
           QE environment of cv1 by an other (as QE environment of cv1
           is attached to a content-host),
           choose DEV and content view cv1 as a replacement for Content-host
           and for Activation key.
        8. Refresh content-host subscription

        @Assert:

        1. Activation key exists
        2. Content-host exists
        3. QE environment of cv1 was replaced by DEV environment of cv1
           in activation key
        4. QE environment of cv1 was replaced by DEV environment of cv1
           in content-host
        5. At content-host some package from cv1 is installable

        @caseautomation: notautomated

        @CaseLevel: System
        """

    @stubbed()
    @run_only_on('sat')
    @tier3
    def test_positive_delete_cv_multi_env_promoted_with_host_registered(self):
        """Delete published content view with version promoted to multiple
         environments, with one of the environments used in association of an
         Activation key and content-host registration.

        @id: 73453c99-8f34-413d-8f95-e4a2f4c58a00

        @Steps:

        1. Create two content view cv1 and cv2
        2. Add a yum repo and a puppet module to both content views
        3. Publish the content views
        4. Promote the content views to multiple environment
           Library -> DEV -> QE
        5. Create an Activation key with the QE environment and cv1
        6. Register a content-host using the Activation key
        7. Delete the content view cv1.
           The delete content view wizard should propose to replace the current
           QE environment of cv1 by an other (as QE environment of cv1
           is attached to a content-host), choose DEV and content view cv2
           as a replacement for Content-host and for Activation key.
        8. Refresh content-host subscription

        @Assert:

        1. The content view cv1 doesn't exist
        2. Activation key exists
        3. Content-host exists
        4. QE environment of cv1 was replaced by DEV environment of cv2
           in activation key
        5. QE environment of cv1 was replaced by DEV environment of cv2
           in content-host
        6. At content-host some package from cv2 is installable

        @caseautomation: notautomated

        @CaseLevel: System
        """

    @stubbed()
    @run_only_on('sat')
    @tier3
    def test_positive_remove_cv_version_from_multi_env_capsule_scenario(self):
        """Remove promoted content view version from multiple environment,
        with satellite setup to use capsule

        @id: ba731272-66e6-461e-8e9d-564b4092a92d

        @Steps:

        1. Create a content view
        2. Setup satellite to use a capsule and to sync all lifecycle
           environments
        3. Add a yum repo, puppet module and a docker repo to the content view
        4. Publish the content view
        5. Promote the content view to multiple environment
           Library -> DEV -> QE -> PROD
        6. Make sure the capsule is updated (content synchronization may be
           applied)
        7. Disconnect the capsule
        8. Remove the content view version from Library and DEV environments
           and assert successful completion
        9. Bring the capsule back online and assert that the task is completed
           in capsule
        10. Make sure the capsule is updated (content synchronization may be
            applied)

        @Assert: content view version in capsule is removed from Library
        and DEV and exists only in QE and PROD

        @caseautomation: notautomated

        @CaseLevel: System
        """
        # Note: This test case requires complete external capsule
        #  configuration.

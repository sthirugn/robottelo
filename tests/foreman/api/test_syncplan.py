"""Unit tests for the ``sync_plans`` paths.

A full API reference for sync plans can be found here:
http://www.katello.org/docs/api/apidoc/sync_plans.html


@Requirement: Syncplan

@CaseAutomation: Automated

@CaseLevel: Acceptance

@CaseComponent: API

@TestType: Functional

@CaseImportance: High

@Upstream: No
"""
import random
from datetime import datetime, timedelta
from fauxfactory import gen_string
from nailgun import client, entities
from random import sample
from robottelo import manifests
from robottelo.api.utils import enable_rhrepo_and_fetchid
from robottelo.config import settings
from robottelo.constants import PRDS, REPOS, REPOSET
from robottelo.datafactory import (
    filtered_datapoint,
    invalid_values_list,
    valid_data_list,
)
from requests.exceptions import HTTPError
from robottelo.decorators import (
    run_in_one_thread,
    run_only_on,
    skip_if_bug_open,
    stubbed,
    tier1,
    tier2,
    tier4
)
from robottelo.test import APITestCase
from time import sleep


@filtered_datapoint
def valid_sync_dates():
    """Returns a list of valid sync dates."""
    return [
        # Today
        datetime.now(),
        # 5 minutes from now
        datetime.now() + timedelta(seconds=300),
        # 5 days from now
        datetime.now() + timedelta(days=5),
        # Yesterday
        datetime.now() - timedelta(days=1),
        # 5 minutes ago
        datetime.now() - timedelta(seconds=300),
    ]


@filtered_datapoint
def valid_sync_interval():
    """Returns a list of valid sync intervals."""
    return [u'hourly', u'daily', u'weekly']


class SyncPlanTestCase(APITestCase):
    """Miscellaneous tests for sync plans."""

    @tier1
    def test_positive_get_routes(self):
        """Issue an HTTP GET response to both available routes.

        @id: 9e40ea7f-71ea-4ced-94ba-cde03620c654

        @Assert: The same response is returned.

        Targets BZ 1132817.
        """
        org = entities.Organization().create()
        entities.SyncPlan(organization=org).create()
        response1 = client.get(
            '{0}/katello/api/v2/sync_plans'.format(settings.server.get_url()),
            auth=settings.server.get_credentials(),
            data={'organization_id': org.id},
            verify=False,
        )
        response2 = client.get(
            '{0}/katello/api/v2/organizations/{1}/sync_plans'.format(
                settings.server.get_url(),
                org.id
            ),
            auth=settings.server.get_credentials(),
            verify=False,
        )
        for response in (response1, response2):
            response.raise_for_status()
        self.assertEqual(
            response1.json()['results'],
            response2.json()['results'],
        )


class SyncPlanCreateTestCase(APITestCase):
    """Tests specific to creating new sync plans."""

    @classmethod
    def setUpClass(cls):
        """Create an organization which can be re-used in tests."""
        super(SyncPlanCreateTestCase, cls).setUpClass()
        cls.org = entities.Organization().create()

    @run_only_on('sat')
    @tier1
    def test_positive_create_enabled_disabled(self):
        """Create sync plan with different 'enabled' field values.

        @id: df5837e7-3d0f-464a-bd67-86b423c16eb4

        @Assert: A sync plan is created, 'enabled' field has correct value.
        """
        for enabled in (False, True):
            with self.subTest(enabled):
                sync_plan = entities.SyncPlan(
                    enabled=enabled,
                    organization=self.org,
                ).create()
                self.assertEqual(sync_plan.enabled, enabled)

    @run_only_on('sat')
    @tier1
    def test_positive_create_with_name(self):
        """Create a sync plan with a random name.

        @id: c1263134-0d7c-425a-82fd-df5274e1f9ba

        @Assert: A sync plan is created with the specified name.
        """
        for name in valid_data_list():
            with self.subTest(name):
                syncplan = entities.SyncPlan(
                    name=name,
                    organization=self.org
                ).create()
                self.assertEqual(syncplan.name, name)

    @run_only_on('sat')
    @tier1
    def test_positive_create_with_description(self):
        """Create a sync plan with a random description.

        @id: 3e5745e8-838d-44a5-ad61-7e56829ad47c

        @Assert: A sync plan is created with the specified description.
        """
        for description in valid_data_list():
            with self.subTest(description):
                sync_plan = entities.SyncPlan(
                    description=description,
                    organization=self.org,
                ).create()
                self.assertEqual(sync_plan.description, description)

    @run_only_on('sat')
    @tier1
    def test_positive_create_with_interval(self):
        """Create a sync plan with a random interval.

        @id: d160ed1c-b698-42dc-be0b-67ac693c7840

        @Assert: A sync plan is created with the specified interval.
        """
        for interval in valid_sync_interval():
            with self.subTest(interval):
                sync_plan = entities.SyncPlan(
                    interval=interval,
                    organization=self.org,
                ).create()
                self.assertEqual(sync_plan.interval, interval)

    @run_only_on('sat')
    @tier1
    def test_positive_create_with_sync_date(self):
        """Create a sync plan and update its sync date.

        @id: bdb6e0a9-0d3b-4811-83e2-2140b7bb62e3

        @Assert: A sync plan can be created with a random sync date.
        """
        for syncdate in valid_sync_dates():
            with self.subTest(syncdate):
                sync_plan = entities.SyncPlan(
                    organization=self.org,
                    sync_date=syncdate,
                ).create()
                self.assertEqual(
                    syncdate.strftime('%Y/%m/%d %H:%M:%S UTC'),
                    sync_plan.sync_date
                )

    @run_only_on('sat')
    @tier1
    def test_negative_create_with_invalid_name(self):
        """Create a sync plan with an invalid name.

        @id: a3a0f844-2f81-4f87-9f68-c25506c29ce2

        @Assert: A sync plan can not be created with the specified name.
        """
        for name in invalid_values_list():
            with self.subTest(name):
                with self.assertRaises(HTTPError):
                    entities.SyncPlan(
                        name=name,
                        organization=self.org
                    ).create()

    @run_only_on('sat')
    @tier1
    def test_negative_create_with_invalid_interval(self):
        """Create a sync plan with invalid interval specified.

        @id: f5844526-9f58-4be3-8a96-3849a465fc02

        @Assert: A sync plan can not be created with invalid interval specified
        """
        for interval in invalid_values_list():
            with self.subTest(interval):
                with self.assertRaises(HTTPError):
                    entities.SyncPlan(
                        interval=interval,
                        organization=self.org,
                    ).create()

    @run_only_on('sat')
    @tier1
    def test_negative_create_with_empty_interval(self):
        """Create a sync plan with no interval specified.

        @id: b4686463-69c8-4538-b040-6fb5246a7b00

        @Assert: A sync plan can not be created with no interval specified.
        """
        sync_plan = entities.SyncPlan(organization=self.org)
        sync_plan.create_missing()
        del sync_plan.interval
        with self.assertRaises(HTTPError):
            sync_plan.create(False)


class SyncPlanUpdateTestCase(APITestCase):
    """Tests specific to updating a sync plan."""

    @classmethod
    def setUpClass(cls):
        """Create an organization which can be re-used in tests."""
        super(SyncPlanUpdateTestCase, cls).setUpClass()
        cls.org = entities.Organization().create()

    @run_only_on('sat')
    @tier1
    def test_positive_update_enabled(self):
        """Create sync plan and update it with opposite 'enabled' value.

        @id: 325c0ef5-c0e8-4cb9-b85e-87eb7f42c2f8

        @Assert: Sync plan is updated with different 'enabled' value.
        """
        for enabled in (False, True):
            with self.subTest(enabled):
                sync_plan = entities.SyncPlan(
                    enabled=not enabled,
                    organization=self.org,
                ).create()
                sync_plan.enabled = enabled
                self.assertEqual(
                    sync_plan.update(['enabled']).enabled,
                    enabled
                )

    @run_only_on('sat')
    @tier1
    def test_positive_update_name(self):
        """Create a sync plan and update its name.

        @id: dbfadf4f-50af-4aa8-8d7d-43988dc4528f

        @Assert: A sync plan is created and its name can be updated with the
        specified name.
        """
        sync_plan = entities.SyncPlan(organization=self.org).create()
        for name in valid_data_list():
            with self.subTest(name):
                sync_plan.name = name
                self.assertEqual(sync_plan.update(['name']).name, name)

    @tier1
    @run_only_on('sat')
    def test_positive_update_description(self):
        """Create a sync plan and update its description.

        @id: 4769fe9c-9eec-40c8-b015-1e3d7e570bec

        @Assert: A sync plan is created and its description can be updated with
        the specified description.
        """
        sync_plan = entities.SyncPlan(
            description=gen_string('alpha'),
            organization=self.org,
        ).create()
        for description in valid_data_list():
            with self.subTest(description):
                sync_plan.description = description
                self.assertEqual(
                    sync_plan.update(['description']).description,
                    description
                )

    @tier1
    @run_only_on('sat')
    def test_positive_update_interval(self):
        """Create a sync plan and update its interval.

        @id: cf2eddf8-b4db-430e-a9b0-83c626b45068

        @Assert: A sync plan is created and its interval can be updated with
        the specified interval.
        """
        for interval in valid_sync_interval():
            with self.subTest(interval):
                sync_plan = entities.SyncPlan(organization=self.org)
                result = sync_plan.get_fields()['interval']
                sync_plan.interval = sample(
                    set(result.choices) - set([interval]),
                    1
                )[0]
                sync_plan = sync_plan.create()
                sync_plan.interval = interval
                self.assertEqual(
                    sync_plan.update(['interval']).interval,
                    interval
                )

    @run_only_on('sat')
    @tier1
    def test_positive_update_sync_date(self):
        """Updated sync plan's sync date.

        @id: fad472c7-01b4-453b-ae33-0845c9e0dfd4

        @Assert: Sync date is updated with the specified sync date.
        """
        sync_plan = entities.SyncPlan(
            organization=self.org,
            sync_date=datetime.now() + timedelta(days=10),
            ).create()
        for syncdate in valid_sync_dates():
            with self.subTest(syncdate):
                sync_plan.sync_date = syncdate
                self.assertEqual(
                    syncdate.strftime('%Y/%m/%d %H:%M:%S UTC'),
                    sync_plan.update(['sync_date']).sync_date
                )

    @tier1
    @run_only_on('sat')
    def test_negative_update_name(self):
        """Try to update a sync plan with an invalid name.

        @id: ae502053-9d3c-4cad-aee4-821f846ceae5

        @Assert: A sync plan can not be updated with the specified name.
        """
        sync_plan = entities.SyncPlan(organization=self.org).create()
        for name in invalid_values_list():
            with self.subTest(name):
                sync_plan.name = name
                with self.assertRaises(HTTPError):
                    sync_plan.update(['name'])

    @tier1
    @run_only_on('sat')
    def test_negative_update_interval(self):
        """Try to update a sync plan with invalid interval.

        @id: 8c981174-6f55-49c0-8baa-40e5c3fc598c

        @Assert: A sync plan can not be updated with empty interval specified.
        """
        sync_plan = entities.SyncPlan(organization=self.org).create()
        for interval in invalid_values_list():
            with self.subTest(interval):
                sync_plan.interval = interval
                with self.assertRaises(HTTPError):
                    sync_plan.update(['interval'])


class SyncPlanProductTestCase(APITestCase):
    """Tests specific to adding/removing products to sync plans."""

    @classmethod
    def setUpClass(cls):
        """Create an organization and products which can be re-used in
        tests.
        """
        super(SyncPlanProductTestCase, cls).setUpClass()
        cls.org = entities.Organization().create()

    @tier2
    @run_only_on('sat')
    def test_positive_add_product(self):
        """Create a sync plan and add one product to it.

        @id: 036dea02-f73d-4fc1-9c41-5515b6659c79

        @Assert: A sync plan can be created and one product can be added to it.

        @CaseLevel: Integration
        """
        syncplan = entities.SyncPlan(organization=self.org).create()
        product = entities.Product(organization=self.org).create()
        syncplan.add_products(data={'product_ids': [product.id]})
        syncplan = syncplan.read()
        self.assertEqual(len(syncplan.product), 1)
        self.assertEqual(syncplan.product[0].id, product.id)

    @tier2
    @run_only_on('sat')
    def test_positive_add_products(self):
        """Create a sync plan and add two products to it.

        @id: 2a80ecad-2245-46d8-bbc6-0b802e68d50c

        @Assert: A sync plan can be created and two products can be added to
        it.

        @CaseLevel: Integration
        """
        syncplan = entities.SyncPlan(organization=self.org).create()
        products = [
            entities.Product(organization=self.org).create() for _ in range(2)
        ]
        syncplan.add_products(data={
            'product_ids': [product.id for product in products],
        })
        syncplan = syncplan.read()
        self.assertEqual(len(syncplan.product), 2)
        self.assertEqual(
            set((product.id for product in products)),
            set((product.id for product in syncplan.product)),
        )

    @tier2
    @skip_if_bug_open('bugzilla', 1199150)
    @run_only_on('sat')
    def test_positive_remove_product(self):
        """Create a sync plan with two products and then remove one
        product from it.

        @id: 987a0d94-ceb7-4115-9770-2297e60a63fa

        @Assert: A sync plan can be created and one product can be removed from
        it.

        @CaseLevel: Integration
        """
        syncplan = entities.SyncPlan(organization=self.org).create()
        products = [
            entities.Product(organization=self.org).create() for _ in range(2)
        ]
        syncplan.add_products(data={
            'product_ids': [product.id for product in products],
        })
        self.assertEqual(len(syncplan.read().product), 2)
        syncplan.remove_products(data={'product_ids': [products[0].id]})
        syncplan = syncplan.read()
        self.assertEqual(len(syncplan.product), 1)
        self.assertEqual(syncplan.product[0].id, products[1].id)

    @tier2
    @run_only_on('sat')
    def test_positive_remove_products(self):
        """Create a sync plan with two products and then remove both
        products from it.

        @id: eed8c239-8ba3-4dbd-aa6b-c289cd4efd47

        @Assert: A sync plan can be created and both products can be removed
        from it.

        @CaseLevel: Integration
        """
        syncplan = entities.SyncPlan(organization=self.org).create()
        products = [
            entities.Product(organization=self.org).create() for _ in range(2)
        ]
        syncplan.add_products(data={
            'product_ids': [product.id for product in products],
        })
        self.assertEqual(len(syncplan.read().product), 2)
        syncplan.remove_products(data={
            'product_ids': [product.id for product in products],
        })
        self.assertEqual(len(syncplan.read().product), 0)

    @tier2
    @skip_if_bug_open('bugzilla', 1199150)
    @run_only_on('sat')
    def test_positive_repeatedly_add_remove(self):
        """Repeatedly add and remove a product from a sync plan.

        @id: b67536ba-3a36-4bb7-a405-0e12081d5a7e

        @Assert: A task is returned which can be used to monitor the additions
        and removals.

        @CaseLevel: Integration
        """
        syncplan = entities.SyncPlan(organization=self.org).create()
        product = entities.Product(organization=self.org).create()
        for _ in range(5):
            syncplan.add_products(data={'product_ids': [product.id]})
            self.assertEqual(len(syncplan.read().product), 1)
            syncplan.remove_products(data={'product_ids': [product.id]})
            self.assertEqual(len(syncplan.read().product), 0)


class SyncPlanSynchronizeTestCase(APITestCase):
    """Tests specific to synchronizing sync plans."""

    @classmethod
    def setUpClass(cls):
        """Create an organization which can be re-used in tests."""
        super(SyncPlanSynchronizeTestCase, cls).setUpClass()
        cls.org = entities.Organization().create()

    def validate_repo_content(
            self, repo, content_types, after_sync=True, max_attempts=10):
        """Check whether corresponding content is present in repository before
        or after synchronization is performed

        :param repo: Repository entity instance to be validated
        :param content_types: List of repository content entities that
            should be validated (e.g. package, erratum, puppet_module)
        :param bool after_sync: Specify whether you perform validation before
            synchronization procedure is happened or after
        :param int max_attempts: That value is basically introduced for slow
            systems when user sure that sync procedure can take more than 300
            seconds (30*10 where 10 is a default value for max_attempts
            variable)

        """
        for _ in range(max_attempts):
            try:
                repo = repo.read()
                for content in content_types:
                    if after_sync:
                        self.assertGreater(repo.content_counts[content], 0)
                    else:
                        self.assertFalse(repo.content_counts[content])
                break
            except AssertionError:
                sleep(30)
        else:
            raise AssertionError(
                'Repository contains invalid number of content entities')

    # This Bugzilla bug is private. It is impossible to fetch info about it.
    @stubbed('Unstub when BZ1279539 is fixed')
    @tier4
    def test_negative_synchronize_custom_product_current_sync_date(self):
        """Verify product won't get synced immediately after adding association
        with a sync plan which has already been started

        @id: 263a6a79-8236-4757-bf9e-8d9091ba2a11

        @Assert: Product was not synchronized

        @BZ: 1279539

        @CaseLevel: System
        """
        sync_plan = entities.SyncPlan(
            organization=self.org,
            enabled=True,
            sync_date=datetime.utcnow(),
        ).create()
        product = entities.Product(organization=self.org).create()
        repo = entities.Repository(product=product).create()
        # Verify product is not synced and doesn't have any content
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'], after_sync=False)
        # Associate sync plan with product
        sync_plan.add_products(data={'product_ids': [product.id]})
        # Verify product was not synced right after it was added to sync plan
        with self.assertRaises(AssertionError):
            self.validate_repo_content(
                repo,
                ['erratum', 'package', 'package_group'],
                max_attempts=5,
            )

    @stubbed('Unstub when BZ1279539 is fixed')
    @tier4
    def test_positive_synchronize_custom_product_current_sync_date(self):
        """Create a sync plan with current datetime as a sync date, add a
        custom product and verify the product gets synchronized on the next
        sync occurrence

        @id: 0495cb39-2f15-4b6e-9828-1e9517c5c826

        @Assert: Product is synchronized successfully.

        @BZ: 1279539

        @CaseLevel: System
        """
        interval = 60 * 60  # 'hourly' sync interval in seconds
        sync_plan = entities.SyncPlan(
            organization=self.org,
            enabled=True,
            interval=u'hourly',
            sync_date=datetime.utcnow(),
        ).create()
        product = entities.Product(organization=self.org).create()
        repo = entities.Repository(product=product).create()
        # Associate sync plan with product
        sync_plan.add_products(data={'product_ids': [product.id]})
        # Wait half of expected time
        sleep(interval / 2)
        # Verify product is not synced and doesn't have any content
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'], after_sync=False)
        # Wait the rest of expected time
        sleep(interval / 2)
        # Verify product was synced successfully
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'])

    @tier4
    def test_positive_synchronize_custom_product_future_sync_date(self):
        """Create a sync plan with sync date in a future and sync one custom
        product with it automatically.

        @id: b70a0c50-7335-4285-b24c-edfc1187f034

        @Assert: Product is synchronized successfully.

        @CaseLevel: System
        """
        delay = 10 * 60  # delay for sync date in seconds
        sync_plan = entities.SyncPlan(
            organization=self.org,
            enabled=True,
            sync_date=datetime.utcnow() + timedelta(seconds=delay),
        ).create()
        product = entities.Product(organization=self.org).create()
        repo = entities.Repository(product=product).create()
        # Verify product is not synced and doesn't have any content
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'], after_sync=False)
        # Associate sync plan with product
        sync_plan.add_products(data={'product_ids': [product.id]})
        # Wait half of expected time
        sleep(delay/2)
        # Verify product has not been synced yet
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'], after_sync=False)
        # Wait the rest of expected time
        sleep(delay/2)
        # Verify product was synced successfully
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'])

    @tier4
    def test_positive_synchronize_custom_products_future_sync_date(self):
        """Create a sync plan with sync date in a future and sync multiple
        custom products with multiple repos automatically.

        @id: e646196e-3951-4297-8c3c-1494d9895347

        @Assert: Products are synchronized successfully.

        @CaseLevel: System
        """
        delay = 10 * 60  # delay for sync date in seconds
        sync_plan = entities.SyncPlan(
            organization=self.org,
            enabled=True,
            sync_date=datetime.utcnow() + timedelta(seconds=delay),
        ).create()
        products = [
            entities.Product(organization=self.org).create()
            for _ in range(random.randint(3, 5))
        ]
        repos = [
            entities.Repository(product=product).create()
            for product in products
            for _ in range(random.randint(2, 3))
        ]
        # Verify products have not been synced yet
        for repo in repos:
            self.validate_repo_content(
                repo,
                ['erratum', 'package', 'package_group'],
                after_sync=False,
            )
        # Associate sync plan with products
        sync_plan.add_products(data={
            'product_ids': [product.id for product in products]})
        # Wait half of expected time
        sleep(delay/2)
        # Verify products has not been synced yet
        for repo in repos:
            self.validate_repo_content(
                repo,
                ['erratum', 'package', 'package_group'],
                after_sync=False,
            )
        # Wait the rest of expected time
        sleep(delay/2)
        # Verify product was synced successfully
        for repo in repos:
            self.validate_repo_content(
                repo, ['erratum', 'package', 'package_group'])

    @run_in_one_thread
    @stubbed('Unstub when BZ1279539 is fixed')
    @tier4
    def test_positive_synchronize_rh_product_current_sync_date(self):
        """Create a sync plan with current datetime as a sync date, add a
        RH product and verify the product gets synchronized on the next sync
        occurrence

        @id: 080c316d-4a06-4ee9-b5f6-1b210d8d0593

        @Assert: Product is synchronized successfully.

        @BZ: 1279539

        @CaseLevel: System
        """
        interval = 60 * 60  # 'hourly' sync interval in seconds
        org = entities.Organization().create()
        with manifests.clone() as manifest:
            entities.Subscription().upload(
                data={'organization_id': org.id},
                files={'content': manifest.content},
            )
        repo_id = enable_rhrepo_and_fetchid(
            basearch='x86_64',
            org_id=org.id,
            product=PRDS['rhel'],
            repo=REPOS['rhst7']['name'],
            reposet=REPOSET['rhst7'],
            releasever=None,
        )
        product = entities.Product(
            name=PRDS['rhel'],
            organization=org,
        ).search()[0]
        repo = entities.Repository(id=repo_id).read()
        sync_plan = entities.SyncPlan(
            organization=org,
            enabled=True,
            interval=u'hourly',
            sync_date=datetime.utcnow(),
        ).create()
        # Associate sync plan with product
        sync_plan.add_products(data={'product_ids': [product.id]})
        # Wait half of expected time
        sleep(interval / 2)
        # Verify product has not been synced yet
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'], after_sync=False)
        # Wait the rest of expected time
        sleep(interval / 2)
        # Verify product was synced successfully
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'])

    @run_in_one_thread
    @tier4
    def test_positive_synchronize_rh_product_future_sync_date(self):
        """Create a sync plan with sync date in a future and sync one RH
        product with it automatically.

        @id: 6697a00f-2181-4c2b-88eb-2333268d780b

        @Assert: Product is synchronized successfully.

        @CaseLevel: System
        """
        delay = 10 * 60  # delay for sync date in seconds
        org = entities.Organization().create()
        with manifests.clone() as manifest:
            entities.Subscription().upload(
                data={'organization_id': org.id},
                files={'content': manifest.content},
            )
        sync_plan = entities.SyncPlan(
            organization=org,
            enabled=True,
            interval=u'hourly',
            sync_date=datetime.utcnow() + timedelta(seconds=delay),
        ).create()
        repo_id = enable_rhrepo_and_fetchid(
            basearch='x86_64',
            org_id=org.id,
            product=PRDS['rhel'],
            repo=REPOS['rhst7']['name'],
            reposet=REPOSET['rhst7'],
            releasever=None,
        )
        product = entities.Product(
            name=PRDS['rhel'],
            organization=org,
        ).search()[0]
        repo = entities.Repository(id=repo_id).read()
        # Associate sync plan with product
        sync_plan.add_products(data={'product_ids': [product.id]})
        # Verify product is not synced and doesn't have any content
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'], after_sync=False)
        # Wait half of expected time
        sleep(delay/2)
        # Verify product has not been synced yet
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'], after_sync=False)
        # Wait the rest of expected time
        sleep(delay/2)
        # Verify product was synced successfully
        self.validate_repo_content(
            repo, ['erratum', 'package', 'package_group'])


class SyncPlanDeleteTestCase(APITestCase):
    """Tests specific to deleting sync plans."""

    @classmethod
    def setUpClass(cls):
        """Create an organization which can be re-used in tests."""
        super(SyncPlanDeleteTestCase, cls).setUpClass()
        cls.org = entities.Organization().create()

    @tier2
    @run_only_on('sat')
    def test_positive_delete_one_product(self):
        """Create a sync plan with one product and delete it.

        @id: e565c464-33e2-4bca-8eca-15d5a7d4b155

        @Assert: A sync plan is created with one product and sync plan can be
        deleted.

        @CaseLevel: Integration
        """
        sync_plan = entities.SyncPlan(organization=self.org).create()
        product = entities.Product(organization=self.org).create()
        sync_plan.add_products(data={'product_ids': [product.id]})
        sync_plan.delete()
        with self.assertRaises(HTTPError):
            sync_plan.read()

    @tier2
    @run_only_on('sat')
    def test_positive_delete_products(self):
        """Create a sync plan with two products and delete them.

        @id: f21bd57f-369e-4acd-a492-5532349a3804

        @Assert: A sync plan is created with one product and sync plan can be
        deleted.

        @CaseLevel: Integration
        """
        sync_plan = entities.SyncPlan(organization=self.org).create()
        products = [
            entities.Product(organization=self.org).create() for _ in range(2)
        ]
        sync_plan.add_products(data={
            'product_ids': [product.id for product in products],
        })
        sync_plan.delete()
        with self.assertRaises(HTTPError):
            sync_plan.read()

    @tier2
    @run_only_on('sat')
    def test_positive_delete_synced_product(self):
        """Create a sync plan with one synced product and delete it.

        @id: 195d8fec-1fa0-42ab-84a5-32dd81a285ca

        @Assert: A sync plan is created with one synced product and sync plan
        can be deleted.

        @CaseLevel: Integration
        """
        sync_plan = entities.SyncPlan(organization=self.org).create()
        product = entities.Product(organization=self.org).create()
        entities.Repository(product=product).create()
        sync_plan.add_products(data={'product_ids': [product.id]})
        product.sync()
        sync_plan.delete()
        with self.assertRaises(HTTPError):
            sync_plan.read()

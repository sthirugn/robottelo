# -*- encoding: utf-8 -*-
# vim: ts=4 sw=4 expandtab ai

"""
Test class for Users UI
"""

import sys
if sys.hexversion >= 0x2070000:
    import unittest
else:
    import unittest2 as unittest

from ddt import data, ddt
from nose.plugins.attrib import attr
from robottelo.common.constants import NOT_IMPLEMENTED, LANGUAGES
from robottelo.common.helpers import (generate_email_address,
                                      generate_string)
from robottelo.ui.factory import make_org
from robottelo.ui.session import Session
from robottelo.ui.locators import common_locators, tab_locators, locators
from tests.foreman.ui.baseui import BaseUI


def gen_valid_strings(len1=255):
    """
    Generates a list of all the input strings,
    (excluding html)
    """
    valid_names = [
        generate_string("alpha", 5),
        generate_string("alpha", len1),
        u"%s-%s" % (generate_string("alpha", 4),
                    generate_string("alpha", 4),),
        u"%s.%s" % (generate_string("alpha", 4),
                    generate_string("alpha", 4),),
        u"նոր օգտվող-%s" % generate_string("alpha", 2),
        u"新用戶-%s" % generate_string("alpha", 2),
        u"नए उपयोगकर्ता-%s" % generate_string("alpha", 2),
        u"нового пользователя-%s" % generate_string("alpha", 2),
        u"uusi käyttäjä-%s" % generate_string("alpha", 2),
        u"νέος χρήστης-%s" % generate_string("alpha", 2),
        u"foo@!#$^&*( ) %s" % generate_string("alpha", 2),
        u"bar+{}|\"?hi %s" % generate_string("alpha", 2),
    ]

    return valid_names


def gen_valid_usernames(len1=100):
    """
    Generates a list of all the input strings,
    (excluding html)
    """
    valid_names = [
        generate_string("alpha", 5),
        generate_string("alpha", len1),
        u"%s-%s" % (generate_string("alpha", 4), generate_string("alpha", 4)),
        u"%s.%s" % (generate_string("alpha", 4), generate_string("alpha", 4)),
        u"նորօգտվող-%s" % generate_string("alpha", 2),
        u"新用戶-%s" % generate_string("alpha", 2),
        # TODO: determine why this string is rejected.
        # u"नएउपयोगकर्ता-%s" % generate_name(2),
        u"новогопользователя-%s" % generate_string("alpha", 2),
        u"uusikäyttäjä-%s" % generate_string("alpha", 2),
        u"νέοςχρήστης-%s" % generate_string("alpha", 2),
    ]

    return valid_names


def gen_invalid_strings():
    """
    List of invalid names for input testing.
    (exluding strings padded with whitespace)
    """
    invalid_names = [
        u" ",
        generate_string("alpha", 300),
        generate_string("numeric", 300),
        generate_string("alphanumeric", 300),
        generate_string("utf8", 300),
        generate_string("latin1", 300),
        generate_string("html", 300),
        generate_string("alpha", 256)
    ]
    return invalid_names


def gen_invalid_surnames():
    """
    List of invalid names for input testing.
    (exluding strings with whitespace)
    """
    invalid_names = [
        generate_string("alpha", 300),
        generate_string("numeric", 300),
        generate_string("alphanumeric", 300),
        generate_string("utf8", 300),
        generate_string("latin1", 300),
        generate_string("html", 300),
        generate_string("alpha", 256)
    ]
    return invalid_names


@ddt
class User(BaseUI):
    """
    Implements Users tests in UI

    [1] Positive Name variations - Alpha, Numeric, Alphanumeric, Symbols,
    Latin1, Multibyte, Max length,  Min length, Max_db_size, html, css,
    javascript, url, shell commands, sql, spaces in name
    [2] Negative Name Variations -  Blank, Greater than Max Length,
    Lesser than Min Length, Greater than Max DB size
    """

    def create_user(self, name=None, password=None,
                    email=None, firstname=None,
                    lastname=None,
                    locale=None, roles=None,
                    organizations=None,
                    locations=None, authorized_by="INTERNAL",
                    password2=None):
        """
        Function to create a new User
        """

        name = name or generate_string("alpha", 8)
        password = password or generate_string("alpha", 8)
        if not password2:
            password2 = password
        email = email or generate_email_address()
        first_name = firstname or generate_string("alpha", 10)
        last_name = lastname or generate_string("alpha", 8)
        self.navigator.go_to_users()
        self.user.create(username=name, email=email,
                         password1=password,
                         password2=password2,
                         first_name=first_name,
                         last_name=last_name,
                         roles=roles,
                         locations=locations,
                         organizations=organizations,
                         locale=locale,
                         authorized_by=authorized_by,
                         edit=True)

    @attr('ui', 'user', 'implemented')
    def test_delete_user(self):
        """
        @Feature: User - Delete
        @Test: Delete a User
        @Assert: User is deleted
        """
        name = generate_string("alpha", 6)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        self.create_user(name)
        self.assertIsNotNone(self.user.search(name, search_key))
        self.user.delete(name, search_key, really=True)
        self.assertTrue(self.user.wait_until_element(common_locators
                                                     ["notif.success"]))
        self.assertIsNone(self.user.search(name, search_key))

    @attr('ui', 'user', 'implemented')
    def test_update_password(self):
        """
        @Feature: User - Update
        @Test: Update password for a user
        @Assert: User password is updated
        """

        name = generate_string("alpha", 6)
        new_password = generate_string("alpha", 8)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        self.create_user(name)
        self.user.update(search_key, name, None, None, new_password)
        self.login.logout()
        self.login.login(name, new_password)
        self.assertTrue(self.login.is_logged())

    @attr('ui', 'user', 'implemented')
    def test_update_role(self):
        """
        @Feature: User - Update
        @Test: Update role for a user
        @Assert: User role is updated
        """

        strategy = common_locators["entity_deselect"][0]
        value = common_locators["entity_deselect"][1]
        name = generate_string("alpha", 6)
        role = generate_string("alpha", 6)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        self.navigator.go_to_roles()
        self.role.create(role)
        self.assertIsNotNone(self, self.role.search(role))
        self.create_user(name)
        self.user.search(name, search_key).click()
        self.user.wait_until_element(tab_locators["users.tab_roles"]).click()
        element1 = self.user.wait_until_element((strategy,
                                                 value % role))
        self.assertIsNone(element1)
        self.user.update(search_key, name, new_roles=[role])
        self.user.search(name, search_key).click()
        self.user.wait_until_element(tab_locators["users.tab_roles"]).click()
        element2 = self.user.wait_until_element((strategy,
                                                value % role))
        self.assertTrue(element2)

    @attr('ui', 'user', 'implemented')
    @data(*gen_valid_usernames())
    def test_positive_create_user_1(self, user_name):
        """
        @Feature: User - Positive Create
        @Test: Create User for all variations of Username
        @Steps:
        1. Create User for all valid Username variation in [1] using
        valid First Name, Surname, Email Address, Language, authorized by
        @Assert: User is created
        @Status: Manual
        """
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(user_name)
        self.assertIsNotNone(self.user.search(user_name, search_key))

    @attr('ui', 'user', 'implemented')
    @data(*gen_valid_usernames(50))
    def test_positive_create_user_2(self, first):
        """
        @Feature: User - Positive Create
        @Test: Create User for all variations of First Name
        @Steps:
        1. Create User for all valid First Name variation in [1] using
        valid Username, Surname, Email Address, Language, authorized by
        @Assert: User is created
        @Status: Manual
        """
        name = generate_string("alpha", 8)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(name, firstname=first)
        element = self.user.search(name, search_key)
        self.assertIsNotNone(element)
        element.click()
        self.assertTrue(self.user.wait_until_element(locators[
            "users.firstname"]).get_attribute("value") == first)

    @attr('ui', 'user', 'implemented')
    @data(*gen_valid_usernames(50))
    def test_positive_create_user_3(self, last_name):
        """
        @Feature: User - Positive Create
        @Test: Create User for all variations of Surname
        @Steps:
        1. Create User for all valid Surname variation in [1] using
        valid Username, First Name, Email Address, Language, authorized by
        @Assert: User is created
        @Status: Manual
        """
        name = generate_string("alpha", 8)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(name, lastname=last_name)
        element = self.user.search(name, search_key)
        self.assertIsNotNone(element)
        element.click()
        self.assertTrue(self.user.wait_until_element(locators[
            "users.lastname"]).get_attribute("value") == last_name)

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_4(self):
        """
        @Feature: User - Positive Create
        @Test: Create User for all variations of Email Address
        @Steps:
        1. Create User for all valid Email Address variation in [1] using
        valid Username, First Name, Surname, Language, authorized by
        @Assert: User is created
        @Status: Manual
        """
        pass

    @attr('ui', 'user', 'implemented')
    @data(*LANGUAGES)
    def test_positive_create_user_5(self, lang):
        """
        @Feature: User - Positive Create
        @Test: Create User for all variations of Language
        @Steps:
        1. Create User for all valid Language variations using
        valid Username, First Name, Surname, Email Address, authorized by
        @Assert: User is created
        @Status: Manual
        """
        name = generate_string("alpha", 8)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(name, locale=lang)
        element = self.user.search(name, search_key)
        self.assertIsNotNone(element)
        element.click()
        self.assertTrue(self.user.wait_until_element(locators[
            "users.selected_lang"]).get_attribute("value") == lang)

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_6(self):
        """
        @Feature: User - Positive Create
        @Test: Create User by choosing Authorized by - INTERNAL
        @Steps:
        1. Create User by choosing Authorized by - INTERNAL using
        valid Password/Verify fields
        @Assert: User is created
        @Status: Manual
        """
        pass

    @attr('ui', 'user', 'implemented')
    @data(*gen_valid_strings())
    def test_positive_create_user_7(self, password):
        """
        @Feature: User - Positive Create
        @Test: Create User for all variations of Password
        @Steps:
        1. Create User for all valid Password variation in [1] using valid
        Username, First Name, Surname, Email Address, Language, authorized by
        @Assert: User is created
        @Status: Manual
        """
        name = generate_string("alpha", 8)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(name, password)
        self.assertIsNotNone(self.user.search(name, search_key))

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_8(self):
        """
        @Feature: User - Positive Create
        @Test: Create an Admin user
        @Assert: Admin User is created
        @Status: Manual
        """
        pass

    @attr('ui', 'user', 'implemented')
    def test_positive_create_user_9(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with one role
        @Steps:
        1. Create User with one role assigned to it
        @Assert: User is created
        @Status: Manual
        """
        strategy = common_locators["entity_deselect"][0]
        value = common_locators["entity_deselect"][1]
        name = generate_string("alpha", 6)
        role = generate_string("alpha", 6)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        self.navigator.go_to_roles()
        self.role.create(role)
        self.assertIsNotNone(self, self.role.search(role))
        self.create_user(name, roles=[role])
        self.user.search(name, search_key).click()
        self.user.wait_until_element(tab_locators["users.tab_roles"]).click()
        element = self.user.wait_until_element((strategy,
                                                value % role))
        self.assertTrue(element)

    @attr('ui', 'user', 'implemented')
    def test_positive_create_user_10(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with multiple roles
        @Steps:
        1. Create User with multiple roles assigned to it
        @Assert: User is created
        @Status: Manual
        """
        strategy = common_locators["entity_deselect"][0]
        value = common_locators["entity_deselect"][1]
        name = generate_string("alpha", 6)
        role1 = generate_string("alpha", 6)
        role2 = generate_string("alpha", 6)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        self.navigator.go_to_roles()
        self.role.create(role1)
        self.role.create(role2)
        self.create_user(name, roles=[role1, role2])
        self.user.search(name, search_key).click()
        self.user.wait_until_element(tab_locators["users.tab_roles"]).click()
        element1 = self.user.wait_until_element((strategy,
                                                value % role1))
        element2 = self.user.wait_until_element((strategy,
                                                value % role2))
        self.assertTrue(element1)
        self.assertTrue(element2)

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_11(self):
        """
        @Feature: User - Positive Create
        @Test: Create User and assign all available roles to it
        @Steps:
        1. Create User with all available roles assigned to it
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_12(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with one owned host
        @Steps:
        1. Create User with one owned host assigned to it
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_13(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with mutiple owned hosts
        @Steps:
        1. Create User with multiple owned hosts assigned to it
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_14(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with all owned hosts
        @Steps:
        1. Create User with all owned hosts assigned to it
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_15(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with one Domain host
        @Steps:
        1. Create User with one Domain host assigned to it
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_16(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with mutiple Domain hosts
        @Steps:
        1. Create User with multiple Domain hosts assigned to it
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_17(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with all Domain hosts
        @Steps:
        1. Create User with all Domain hosts assigned to it
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_18(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with one Compute Resource
        @Steps:
        1. Create User associated with one Compute Resource
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_19(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with mutiple Compute Resources
        @Steps:
        1. Create User associated with multiple Compute Resources
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_20(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with all Compute Resources
        @Steps:
        1. Create User associated with all Compute Resources
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_21(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with one Host group
        @Steps:
        1. Create User associated with one Host group
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_22(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with multiple Host groups
        @Steps:
        1. Create User associated with multiple Host groups
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_23(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with all Host groups
        @Steps:
        1. Create User associated with all available Host groups
        @Assert: User is created
        @Status: Manual
        """
        pass

    @attr('ui', 'user', 'implemented')
    def test_positive_create_user_24(self):
        """
        @Feature: User - Positive Create
        @Test: Create User associated to one Org
        @Assert: User is created
        @Status: Manual
        """
        strategy = common_locators["entity_deselect"][0]
        value = common_locators["entity_deselect"][1]
        name = generate_string("alpha", 6)
        org_name = generate_string("alpha", 6)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        make_org(Session(self.browser), org_name=org_name)
        self.create_user(name, organizations=[org_name])
        self.user.search(name, search_key).click()
        self.user.wait_until_element(
            tab_locators["users.tab_organizations"]).click()
        element = self.user.wait_until_element((strategy,
                                                value % org_name))
        self.assertTrue(element)

    @attr('ui', 'user', 'implemented')
    def test_positive_create_user_25(self):
        """
        @Feature: User - Positive Create
        @Test: Create User associated to multiple Orgs
        @Assert: User is created
        @Status: Manual
        """
        strategy = common_locators["entity_deselect"][0]
        value = common_locators["entity_deselect"][1]
        name = generate_string("alpha", 6)
        org_name1 = generate_string("alpha", 6)
        org_name2 = generate_string("alpha", 6)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        make_org(Session(self.browser), org_name=org_name1)
        make_org(Session(self.browser), org_name=org_name2)
        self.create_user(name, organizations=[org_name1, org_name2])
        self.user.search(name, search_key).click()
        self.user.wait_until_element(
            tab_locators["users.tab_organizations"]).click()
        element1 = self.user.wait_until_element((strategy,
                                                value % org_name1))
        element2 = self.user.wait_until_element((strategy,
                                                 value % org_name2))
        self.assertTrue(element1)
        self.assertTrue(element2)

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_26(self):
        """
        @Feature: User - Positive Create
        @Test: Create User associated to all available Orgs
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_27(self):
        """
        @Feature: User - Positive Create
        @Test: Create User with a new Fact filter
        @Steps:
        1. Create User associating it to a new Fact filter
        @Assert: User is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_user_28(self):
        """
        @Feature: User - Positive Create
        @Test: Create User in supported ldap modes
        @Steps:
        1. Create User in all supported ldap modes - (Active Driectory,
        IPA, Posix)
        @Assert: User is created without specifying the password
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_create_user_1(self):
        """
        @Feature: User - Positive Create
        @Test: [UI ONLY] Attempt to enter all User creation details and Cancel
        @Steps:
        1. Enter all valid Username, First Name, Surname, Email Address,
        Language, authorized by.
        2. Click Cancel
        @Assert: User is not created
        @Status: Manual
        """
        pass

    @attr('ui', 'user', 'implemented')
    @data(*gen_invalid_strings())
    def test_negative_create_user_2(self, user_name):
        """
        @Feature: User - Negative Create
        @Test: Create User with invalid Username
        @Steps:
        1. Create User for all invalid Usernames in [2]
        using valid First Name, Surname, Email Address, Language, authorized by
        @Assert: User is not created. Appropriate error shown.
        @Status: Manual
        """
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(user_name)
        error = self.user.wait_until_element(common_locators["haserror"])
        self.assertTrue(error)

    @attr('ui', 'user', 'implemented')
    @data(*gen_invalid_surnames())
    def test_negative_create_user_3(self, first):
        """
        @Feature: User - Negative Create
        @Test: Create User with invalid Firstname
        @Steps:
        1. Create User for all invalid Firstname in [2]
        using valid Username, Surname, Email Address, Language, authorized by
        @Assert: User is not created. Appropriate error shown.
        @Status: Manual
        """
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(firstname=first)
        error = self.user.wait_until_element(common_locators["haserror"])
        self.assertTrue(error)

    @attr('ui', 'user', 'implemented')
    @data(*gen_invalid_surnames())
    def test_negative_create_user_4(self, last_name):
        """
        @Feature: User - Negative Create
        @Test: Create User with invalid Surname
        @Steps:
        1. Create User for all invalid Surname in [2]
        using valid Username, First Name Email Address, Language, authorized by
        @Assert: User is not created. Appropriate error shown.
        @Status: Manual
        """
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(lastname=last_name)
        error = self.user.wait_until_element(common_locators["haserror"])
        self.assertTrue(error)

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_create_user_5(self):
        """
        @Feature: User - Negative Create
        @Test: Create User with invalid Email Address
        @Steps:
        1. Create User for all invalid Email Address in [2]
        using valid Username, First Name, Surname, Language, authorized by
        @Assert: User is not created. Appropriate error shown.
        @Status: Manual
        """
        pass

    @attr('ui', 'user', 'implemented')
    def test_negative_create_user_6(self):
        """
        @Feature: User - Negative Create
        @Test: Create User with blank Authorized by
        @Steps:
        1. Create User with blank Authorized by
        using valid Username, First Name, Surname, Email Address, Language
        @Assert: User is not created. Appropriate error shown.
        @Status: Manual
        """
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(authorized_by="")
        error = self.user.wait_until_element(common_locators["haserror"])
        self.assertTrue(error)

    @attr('ui', 'user', 'implemented')
    def test_negative_create_user_8(self):
        """
        @Feature: User - Negative Create
        @Test: Create User with non-matching values in Password and verify
        @Steps:
        1. Create User with non-matching values in Password and verify
        using valid Username, First Name, Surname, Email Address, Language,
        authorized by - INTERNAL
        @Assert: User is not created. Appropriate error shown.
        @Status: Manual
        """
        password = generate_string("alpha", 8)
        password2 = generate_string("alpha", 8)
        self.login.login(self.katello_user, self.katello_passwd)
        self.create_user(password=password, password2=password2)
        error = self.user.wait_until_element(common_locators["haserror"])
        self.assertTrue(error)

    @attr('ui', 'user', 'implemented')
    @data(*gen_valid_usernames())
    def test_positive_update_user_1(self, new_username):
        """
        @Feature: User - Positive Update
        @Test: Update Username in User
        @Steps:
        1. Create User
        2. Update User name for all variations in [1]
        @Assert: User is updated
        @Status: Manual
        """
        name = generate_string("alpha", 6)
        password = generate_string("alpha", 8)
        search_key = "login"
        self.login.login(self.katello_user, self.katello_passwd)  # login
        self.create_user(name, password)
        self.user.update(search_key, name, new_username)
        self.assertIsNotNone(
            self.user.search(new_username, search_key))
        self.login.logout()
        self.login.login(new_username, password)
        self.assertTrue(self.login.is_logged())

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_2(self):
        """
        @Feature: User - Positive Update
        @Test: Update Firstname in User
        @Steps:
        1. Create User
        2. Update Firstname name for all variations in [1]
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_3(self):
        """
        @Feature: User - Positive Update
        @Test: Update Surname in User
        @Steps:
        1. Create User
        2. Update Surname for all variations in [1]
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_4(self):
        """
        @Feature: User - Positive Update
        @Test: Update Email Address in User
        @Steps:
        1. Create User
        2. Update Email Address for all variations in [1]
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_5(self):
        """
        @Feature: User - Positive Update
        @Test: Update Language in User
        @Steps:
        1. Create User
        2. Update User with all different Language options
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_6(self):
        """
        @Feature: User - Positive Update
        @Test: Update Password/Verify fields in User
        @Steps:
        1. Create User
        2. Update Password/Verify fields
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_7(self):
        """
        @Feature: User - Positive Update
        @Test: Convert an user from an admin user to non-admin user
        @Steps:
        1. Create User with Administrator rights
        2. Update the User to remove Administrator rights
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_8(self):
        """
        @Feature: User - Positive Update
        @Test: Convert a user to an admin user
        @Steps:
        1. Create a regular (non-admin) user
        2. Update the User to add Administrator rights
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_9(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with one role
        @Steps:
        1. Create User
        2. Assign one role to the user
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_10(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with multiple roles
        @Steps:
        1. Create User
        2. Assign multiple roles to the user
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_11(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with all roles
        @Steps:
        1. Create User
        2. Assign all available roles to the user
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_12(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with one owned host
        @Steps:
        1. Create User
        2. Assign one host to the user
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_13(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with multiple owned hosts
        @Steps:
        1. Create User
        2. Assign multiple owned hosts to the user
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_14(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with all owned hosts
        @Steps:
        1. Create User
        2. Assign all available owned hosts to the user
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_15(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with one Domain host
        @Steps:
        1. Create User
        2. Assign one Domain host to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_16(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with multiple Domain hosts
        @Steps:
        1. Create User
        2. Assign multiple Domain hosts to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_17(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with all Domain hosts
        @Steps:
        1. Create User
        2. Assign all Domain hosts to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_18(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with one Compute Resource
        @Steps:
        1. Create User
        2. Assign one Compute Resource to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_19(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with multiple Compute Resources
        @Steps:
        1. Create User
        2. Assign multiple Compute Resources to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_20(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with all Compute Resources
        @Steps:
        1. Create User
        2. Assign all Compute Resources to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_21(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with one Host group
        @Steps:
        1. Create User
        2. Assign one Host group to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_22(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with multiple Host groups
        @Steps:
        1. Create User
        2. Assign multiple Host groups to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_23(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with all Host groups
        @Steps:
        1. Create User
        2. Assign all available Host groups to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_24(self):
        """
        @Feature: User - Positive Update
        @Test: Assign a User to an Org
        @Steps:
        1. Create User
        2. Assign an Org to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_25(self):
        """
        @Feature: User - Positive Update
        @Test: Assign a User to multiple Orgs
        @Steps:
        1. Create User
        2. Assign multiple Orgs to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_26(self):
        """
        @Feature: User - Positive Update
        @Test: Assign a User to all available Orgs
        @Steps:
        1. Create User
        2. Assign all available Orgs to the User
        @Assert: User is updated
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_update_user_28(self):
        """
        @Feature: User - Positive Update
        @Test: Update User with a new Fact filter
        @Steps:
        1. Create User
        2. Create and assign a new Fact filter to the User
        @Assert: User is update
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_update_user_1(self):
        """
        @Feature: User - Negative Update
        @Test: Update invalid Username in an User
        @Steps:
        1. Create User
        2. Update Username for all variations in [2]
        @Assert: User is not updated.  Appropriate error shown.
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_update_user_2(self):
        """
        @Feature: User - Negative Update
        @Test: Update invalid Firstname in an User
        @Steps:
        1. Create User
        2. Update Firstname for all variations in [2]
        @Assert: User is not updated.  Appropriate error shown.
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_update_user_3(self):
        """
        @Feature: User - Negative Update
        @Test: Update invalid Surname in an User
        @Steps:
        1. Create User
        2. Update Surname for all variations in [2]
        @Assert: User is not updated.  Appropriate error shown.
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_update_user_4(self):
        """
        @Feature: User - Negative Update
        @Test: Update invalid Email Address in an User
        @Steps:
        1. Create User
        2. Update Email Address for all variations in [2]
        @Assert: User is not updated.  Appropriate error shown.
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_update_user_5(self):
        """
        @Feature: User - Negative Update
        @Test: Update different values in Password and verify fields in an User
        @Steps:
        1. Create User
        2. Update the password by entering different values in Password and
        verify fields
        @Assert: User is not updated.  Appropriate error shown.
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_update_user_6(self):
        """
        @Feature: User - Negative Update
        @Test: [UI ONLY] Attempt to update User info and Cancel
        @Steps:
        1. Update Current user with valid Firstname, Surname, Email Address,
        Language, Password/Verify fields
        2. Click Cancel
        @Assert: User is not updated.
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_delete_user_1(self):
        """
        @Feature: User - Positive Delete
        @Test: Delete a user
        @Steps:
        1. Create User
        2. Delete the User
        @Assert: User is deleted
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_delete_user_2(self):
        """
        @Feature: User - Positive Delete
        @Test: Delete an admin user
        @Steps:
        1. Create an admin user
        2. Delete the User
        @Assert: User is deleted
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_delete_user_1(self):
        """
        @Feature: User - Negative Delete
        @Test: [UI ONLY] Attempt to delete an User and cancel
        @Steps:
        1. Create a User
        2. ATtempt to delete the user and click Cancel on the confirmation
        @Assert: User is not deleted
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_delete_user_2(self):
        """
        @Feature: User - Negative Delete
        @Test: Attempt to delete the last remaining admin user
        @Steps:
        1. Create multiple Users and admin users
        2. Delete the users except the last admin user
        3. Attempt to delete the last admin user
        @Assert: User is not deleted
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_list_user_1(self):
        """
        @Feature: User - list
        @Test: List User for all variations of Username
        @Steps:
        1. Create User for all Username variations in [1] using valid
        First Name, Surname, Email Address, Language, authorized by
        2. List User
        @Assert: User is listed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_list_user_2(self):
        """
        @Feature: User - list
        @Test: List User for all variations of Firstname
        @Steps:
        1. Create User for all Firstname variations in [1] using valid
        Username, Surname, Email Address, Language, authorized by
        2. List User
        @Assert: User is listed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_list_user_3(self):
        """
        @Feature: User - list
        @Test: List User for all variations of Surname
        @Steps:
        1. Create User for all Surname variations in [1] using valid
        Username, First Name, Email Address, Language, authorized by
        2. List User
        @Assert: User is listed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_list_user_4(self):
        """
        @Feature: User - list
        @Test: List User for all variations of Email Address
        @Steps:
        1. Create User for all Email Address variations in [1] using valid
        valid Username, First Name, Surname, Language, authorized by
        2. List User
        @Assert: User is listed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_list_user_5(self):
        """
        @Feature: User - list
        @Test: List User for all variations of Language
        @Steps:
        1. Create User for all Language variations using valid
        Username, First Name, Surname, Email Address, authorized by
        2. List User
        @Assert: User is listed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_search_user_1(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Username
        @Steps:
        1. Create User for all Username variations in [1] using valid
        First Name, Surname, Email Address, Language, authorized by
        2. Search/Find User
        @Assert: User is found
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_search_user_2(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Firstname
        @Steps:
        1. Create User for all Firstname variations in [1] using valid
        Username, Surname, Email Address, Language, authorized by
        2. Search/Find User
        @Assert: User is found
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_search_user_3(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Surname
        @Steps:
        1. Create User for all Surname variations in [1] using valid
        Username, First Name, Email Address, Language, authorized by
        2. Search/Find User
        @Assert: User is found
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_search_user_4(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Email Address
        @Steps:
        1. Create User for all Email Address variations in [1] using valid
        valid Username, First Name, Surname, Language, authorized by
        2. Search/Find User
        @Assert: User is found
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_search_user_5(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Language
        @Steps:
        1. Create User for all Language variations using valid
        Username, First Name, Surname, Email Address, authorized by
        2. Search/Find User
        @Assert: User is found
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_info_user_1(self):
        """
        @Feature: User - info
        @Test: Get User info for all variations of Username
        @Steps:
        1. Create User for all Username variations in [1] using valid
        First Name, Surname, Email Address, Language, authorized by
        2. Get info of the User
        @Assert: User info is displayed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_info_user_2(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Firstname
        @Steps:
        1. Create User for all Firstname variations in [1] using valid
        Username, Surname, Email Address, Language, authorized by
        2. Get info of the User
        @Assert: User info is displayed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_info_user_3(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Surname
        @Steps:
        1. Create User for all Surname variations in [1] using valid
        Username, First Name, Email Address, Language, authorized by
        2. Get info of the User
        @Assert: User info is displayed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_info_user_4(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Email Address
        @Steps:
        1. Create User for all Email Address variations in [1] using valid
        valid Username, First Name, Surname, Language, authorized by
        2. Get info of the User
        @Assert: User info is displayed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_info_user_5(self):
        """
        @Feature: User - search
        @Test: Search User for all variations of Language
        @Steps:
        1. Create User for all Language variations using valid
        Username, First Name, Surname, Email Address, authorized by
        2. Get info of the User
        @Assert: User info is displayed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_end_to_end_user_1(self):
        """
        @Feature: User - End to End
        @Test: Create User and perform different operations
        @Steps:
        1. Create User
        2. Login with the new user
        3. Upload Subscriptions
        4. Provision Systems
        5. Add/Remove Users
        6. Add/Remove Orgs
        7. Delete the User
        @Assert: All actions passed
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_end_to_end_user_2(self):
        """
        @Feature: User - End to End
        @Test: Create User with no Org assigned and attempt different
        operations
        @Steps:
        1. Create User.  Do not assign any Org
        2. Login with the new user
        3. Attempt to Upload Subscriptions
        4. Attempt to Provision Systems
        5. Attempt to Add/Remove Users
        6. Attempt to Add/Remove Orgs
        @Assert: All actions failed since the User is not assigned to any Org
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_bookmark_1(self):
        """
        @Feature: Search bookmark - Positive Create
        @Test: Create a bookmark with default values
        @Steps:
        1. Search for a criteria
        2. Create bookmark with default values
        @Assert: Search bookmark is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_bookmark_2(self):
        """
        @Feature: Search bookmark - Positive Create
        @Test: Create a bookmark by altering the default values
        @Steps:
        1. Search for a criteria
        2. Create bookmark updating all the default values
        @Assert: Search bookmark is created
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_bookmark_3(self):
        """
        @Feature: Search bookmark - Positive Create
        @Test: Create a bookmark in public mode
        @Steps:
        1. Search for a criteria
        2. Create bookmark in public mode
        @Assert: Search bookmark is created in public mode and is accessible
        by other users
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_positive_create_bookmark_4(self):
        """
        @Feature: Search bookmark - Positive Create
        @Test: Create a bookmark in private mode
        @Steps:
        1. Search for a criteria
        2. Create bookmark in private mode
        @Assert: Search bookmark is created in private mode and is not
        accessible by other users
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_create_bookmark_1(self):
        """
        @Feature: Search bookmark - Negative Create
        @Test: Create a bookmark with a blank bookmark name
        @Steps:
        1. Search for a criteria
        2. Create bookmark with a blank bookmark name
        @Assert: Search bookmark not created. Appropriate error shown.
        @Status: Manual
        """
        pass

    @unittest.skip(NOT_IMPLEMENTED)
    def test_negative_create_bookmark_2(self):
        """
        @Feature: Search bookmark - Negative Create
        @Test: Create a bookmark with a blank bookmark query
        @Steps:
        1. Search for a criteria
        2. Create bookmark with a blank bookmark query
        @Assert: Search bookmark not created. Appropriate error shown.
        @Status: Manual
        """
        pass

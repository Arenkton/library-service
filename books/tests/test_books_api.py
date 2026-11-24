from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from books.models import Book


User = get_user_model()


class BookAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="reader@example.com",
            password="ReaderPassword123!",
        )
        cls.admin = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
        )

        cls.book = Book.objects.create(
            title="The Hobbit",
            author="J. R. R. Tolkien",
            cover="HARD",
            inventory=5,
            daily_fee="1.50",
        )
        cls.second_book = Book.objects.create(
            title="1984",
            author="George Orwell",
            cover="SOFT",
            inventory=3,
            daily_fee="2.00",
        )

    def setUp(self):
        self.list_url = reverse("book-list")
        self.detail_url = reverse(
            "book-detail", args=[self.book.id]
        )
        self.valid_data = {
            "title": "Dune",
            "author": "Frank Herbert",
            "cover": "SOFT",
            "inventory": 10,
            "daily_fee": "2.50",
        }

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(
            HTTP_AUTHORIZE=f"Bearer {token}"
        )

    def test_anonymous_can_list_books(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        self.assertEqual(len(response.data), 2)

    def test_anonymous_can_retrieve_book(self):
        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        self.assertEqual(response.data["title"], "The Hobbit")

    def test_authenticated_user_can_list_books(self):
        self.authenticate(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )

    def test_anonymous_cannot_create_book(self):
        response = self.client.post(
            self.list_url, self.valid_data, format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_anonymous_cannot_update_book(self):
        response = self.client.patch(
            self.detail_url,
            {"title": "Changed"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_anonymous_cannot_delete_book(self):
        response = self.client.delete(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_regular_user_cannot_create_book(self):
        self.authenticate(self.user)

        response = self.client.post(
            self.list_url, self.valid_data, format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(Book.objects.count(), 2)

    def test_regular_user_cannot_update_book(self):
        self.authenticate(self.user)

        response = self.client.put(
            self.detail_url, self.valid_data, format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_regular_user_cannot_patch_book(self):
        self.authenticate(self.user)

        response = self.client.patch(
            self.detail_url,
            {"inventory": 100},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 5)

    def test_regular_user_cannot_delete_book(self):
        self.authenticate(self.user)

        response = self.client.delete(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertTrue(
            Book.objects.filter(pk=self.book.pk).exists()
        )

    def test_admin_can_create_book(self):
        self.authenticate(self.admin)

        response = self.client.post(
            self.list_url, self.valid_data, format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(Book.objects.count(), 3)
        self.assertEqual(response.data["title"], "Dune")

    def test_admin_can_update_book(self):
        self.authenticate(self.admin)

        response = self.client.put(
            self.detail_url, self.valid_data, format="json"
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "Dune")
        self.assertEqual(self.book.inventory, 10)

    def test_admin_can_patch_book(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            self.detail_url,
            {"inventory": 15},
            format="json",
        )

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )

        self.book.refresh_from_db()
        self.assertEqual(self.book.inventory, 15)

    def test_admin_can_delete_book(self):
        self.authenticate(self.admin)

        response = self.client.delete(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Book.objects.filter(pk=self.book.pk).exists()
        )

    def test_admin_cannot_create_invalid_book(self):
        self.authenticate(self.admin)
        self.valid_data["daily_fee"] = "-2.00"

        response = self.client.post(
            self.list_url, self.valid_data, format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Book.objects.count(), 2)

    def test_book_not_found(self):
        response = self.client.get(
            reverse("book-detail", args=[999999])
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_zero_inventory_book_is_visible(self):
        self.book.inventory = 0
        self.book.save(update_fields=["inventory"])

        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )
        self.assertEqual(response.data["inventory"], 0)

    def test_invalid_jwt_cannot_create_book(self):
        self.client.credentials(
            HTTP_AUTHORIZE="Bearer invalid-token"
        )

        response = self.client.post(
            self.list_url, self.valid_data, format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

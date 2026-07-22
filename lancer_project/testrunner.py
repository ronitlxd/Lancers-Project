"""
Custom test runner — strips the `durations` kwarg on Python < 3.12.

Django 5.x passes `durations` to unittest.TextTestRunner, but that
parameter was only added in Python 3.12.  Without this shim the test
command crashes with:
    TypeError: TextTestRunner.__init__() got an unexpected keyword argument 'durations'
"""
import sys
from django.test.runner import DiscoverRunner


class CompatDiscoverRunner(DiscoverRunner):
    def get_test_runner_kwargs(self):
        kwargs = super().get_test_runner_kwargs()
        if sys.version_info < (3, 12):
            kwargs.pop('durations', None)
        return kwargs

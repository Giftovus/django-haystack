from threading import Thread
import Queue
from django.core.urlresolvers import reverse
from django.conf import settings
from django import forms
from django.http import HttpRequest, QueryDict
from django.test import TestCase
from haystack import connections, connection_router
from haystack.forms import model_choices, SearchForm, ModelSearchForm, FacetedSearchForm
from haystack import indexes
from haystack.query import EmptySearchQuerySet
from haystack.utils.loading import UnifiedIndex
from haystack.views import SearchView, FacetedSearchView, search_view_factory
from core.models import MockModel, AnotherMockModel


class InitialedSearchForm(SearchForm):
    q = forms.CharField(initial='Search for...', required=False, label='Search')


class BasicMockModelSearchIndex(indexes.BasicSearchIndex, indexes.Indexable):
    def get_model(self):
        return MockModel


class BasicAnotherMockModelSearchIndex(indexes.BasicSearchIndex, indexes.Indexable):
    def get_model(self):
        return AnotherMockModel


class SearchViewTestCase(TestCase):
    def setUp(self):
        super(SearchViewTestCase, self).setUp()
        
        # Stow.
        self.old_unified_index = connections['default']._index
        self.ui = UnifiedIndex()
        self.bmmsi = BasicMockModelSearchIndex()
        self.bammsi = BasicAnotherMockModelSearchIndex()
        self.ui.build(indexes=[self.bmmsi, self.bammsi])
        connections['default']._index = self.ui
        
        # Update the "index".
        backend = connections['default'].get_backend()
        backend.clear()
        backend.update(self.bmmsi, MockModel.objects.all())
    
    def tearDown(self):
        connections['default']._index = self.old_unified_index
        super(SearchViewTestCase, self).tearDown()
    
    def test_search_no_query(self):
        response = self.client.get(reverse('haystack_search'))
        self.assertEqual(response.status_code, 200)
    
    def test_search_query(self):
        response = self.client.get(reverse('haystack_search'), {'q': 'haystack'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context[-1]['page'].object_list), 3)
        self.assertEqual(response.context[-1]['page'].object_list[0].content_type(), u'core.mockmodel')
        self.assertEqual(response.context[-1]['page'].object_list[0].pk, '1')
    
    def test_invalid_page(self):
        response = self.client.get(reverse('haystack_search'), {'q': 'haystack', 'page': '165233'})
        self.assertEqual(response.status_code, 404)
    
    def test_empty_results(self):
        sv = SearchView()
        sv.request = HttpRequest()
        sv.form = sv.build_form()
        self.assertTrue(isinstance(sv.get_results(), EmptySearchQuerySet))
    
    def test_initial_data(self):
        sv = SearchView(form_class=InitialedSearchForm)
        sv.request = HttpRequest()
        form = sv.build_form()
        self.assertTrue(isinstance(form, InitialedSearchForm))
        self.assertEqual(form.fields['q'].initial, 'Search for...')
        self.assertEqual(form.as_p(), u'<p><label for="id_q">Search:</label> <input type="text" name="q" value="Search for..." id="id_q" /></p>')
    
    def test_thread_safety(self):
        exceptions = []
        
        def threaded_view(queue, view, request):
            import time; time.sleep(2)
            try:
                inst = view(request)
                queue.put(request.GET['name'])
            except Exception, e:
                exceptions.append(e)
                raise
        
        class ThreadedSearchView(SearchView):
            def __call__(self, request):
                print "Name: %s" % request.GET['name']
                return super(ThreadedSearchView, self).__call__(request)
        
        view = search_view_factory(view_class=ThreadedSearchView)
        queue = Queue.Queue()
        request_1 = HttpRequest()
        request_1.GET = {'name': 'foo'}
        request_2 = HttpRequest()
        request_2.GET = {'name': 'bar'}
        
        th1 = Thread(target=threaded_view, args=(queue, view, request_1))
        th2 = Thread(target=threaded_view, args=(queue, view, request_2))
        
        th1.start()
        th2.start()
        th1.join()
        th2.join()
        
        foo = queue.get()
        bar = queue.get()
        self.assertNotEqual(foo, bar)


class ResultsPerPageTestCase(TestCase):
    urls = 'core.tests.results_per_page_urls'
    
    def setUp(self):
        super(ResultsPerPageTestCase, self).setUp()
        
        # Stow.
        self.old_unified_index = connections['default']._index
        self.ui = UnifiedIndex()
        self.bmmsi = BasicMockModelSearchIndex()
        self.bammsi = BasicAnotherMockModelSearchIndex()
        self.ui.build(indexes=[self.bmmsi, self.bammsi])
        connections['default']._index = self.ui
        
        # Update the "index".
        backend = connections['default'].get_backend()
        backend.clear()
        backend.update(self.bmmsi, MockModel.objects.all())
    
    def tearDown(self):
        connections['default']._index = self.old_unified_index
        super(ResultsPerPageTestCase, self).tearDown()
    
    def test_custom_results_per_page(self):
        response = self.client.get('/search/', {'q': 'haystack'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context[-1]['page'].object_list), 1)
        self.assertEqual(response.context[-1]['paginator'].per_page, 1)
        
        response = self.client.get('/search2/', {'q': 'hello world'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context[-1]['page'].object_list), 2)
        self.assertEqual(response.context[-1]['paginator'].per_page, 2)


class FacetedSearchViewTestCase(TestCase):
    def setUp(self):
        super(FacetedSearchViewTestCase, self).setUp()
        
        # Stow.
        self.old_unified_index = connections['default']._index
        self.ui = UnifiedIndex()
        self.bmmsi = BasicMockModelSearchIndex()
        self.bammsi = BasicAnotherMockModelSearchIndex()
        self.ui.build(indexes=[self.bmmsi, self.bammsi])
        connections['default']._index = self.ui
        
        # Update the "index".
        backend = connections['default'].get_backend()
        backend.clear()
        backend.update(self.bmmsi, MockModel.objects.all())
    
    def tearDown(self):
        connections['default']._index = self.old_unified_index
        super(FacetedSearchViewTestCase, self).tearDown()
    
    def test_search_no_query(self):
        response = self.client.get(reverse('haystack_faceted_search'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['facets'], {})
    
    def test_empty_results(self):
        fsv = FacetedSearchView()
        fsv.request = HttpRequest()
        fsv.request.GET = QueryDict('')
        fsv.form = fsv.build_form()
        self.assertTrue(isinstance(fsv.get_results(), EmptySearchQuerySet))
    
    def test_default_form(self):
        fsv = FacetedSearchView()
        fsv.request = HttpRequest()
        fsv.request.GET = QueryDict('')
        fsv.form = fsv.build_form()
        self.assertTrue(isinstance(fsv.form, FacetedSearchForm))
    
    def test_list_selected_facets(self):
        fsv = FacetedSearchView()
        fsv.request = HttpRequest()
        fsv.request.GET = QueryDict('')
        fsv.form = fsv.build_form()
        self.assertEqual(fsv.form.selected_facets, [])
        
        fsv = FacetedSearchView()
        fsv.request = HttpRequest()
        fsv.request.GET = QueryDict('selected_facets=author:daniel&selected_facets=author:chris')
        fsv.form = fsv.build_form()
        self.assertEqual(fsv.form.selected_facets, [u'author:daniel', u'author:chris'])


class BasicSearchViewTestCase(TestCase):
    def setUp(self):
        super(BasicSearchViewTestCase, self).setUp()
        
        # Stow.
        self.old_unified_index = connections['default']._index
        self.ui = UnifiedIndex()
        self.bmmsi = BasicMockModelSearchIndex()
        self.bammsi = BasicAnotherMockModelSearchIndex()
        self.ui.build(indexes=[self.bmmsi, self.bammsi])
        connections['default']._index = self.ui
        
        # Update the "index".
        backend = connections['default'].get_backend()
        backend.clear()
        backend.update(self.bmmsi, MockModel.objects.all())
    
    def tearDown(self):
        connections['default']._index = self.old_unified_index
        super(BasicSearchViewTestCase, self).tearDown()
    
    def test_search_no_query(self):
        response = self.client.get(reverse('haystack_basic_search'))
        self.assertEqual(response.status_code, 200)
    
    def test_search_query(self):
        response = self.client.get(reverse('haystack_basic_search'), {'q': 'haystack'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(type(response.context[-1]['form']), ModelSearchForm)
        self.assertEqual(len(response.context[-1]['page'].object_list), 3)
        self.assertEqual(response.context[-1]['page'].object_list[0].content_type(), u'core.mockmodel')
        self.assertEqual(response.context[-1]['page'].object_list[0].pk, '1')
        self.assertEqual(response.context[-1]['query'], u'haystack')
    
    def test_invalid_page(self):
        response = self.client.get(reverse('haystack_basic_search'), {'q': 'haystack', 'page': '165233'})
        self.assertEqual(response.status_code, 404)

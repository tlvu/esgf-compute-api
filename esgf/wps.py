""" A WPS Client """

import json

from owslib.wps import WPSExecution
from owslib.wps import WebProcessingService

from lxml import etree

from .errors import WPSClientError
from .process import Process

_IDENTIFICATION = (
    'title',
    'abstract',
    'keywords',
    'accessconstraints',
    'fees',
    'type',
    'service',
    'version',
    'profiles'
)

_PROVIDER = (
    'name',
    'contact',
    'url'
)

_CONTACT = (
    'name',
    'organization',
    'site',
    'position',
    'phone',
    'fax',
    'address',
    'city',
    'region',
    'postcode',
    'country',
    'email',
    'url',
    'hours',
    'instructions'
)

class WPS(object):
    """ WPS client.

    A WPS client built around owslib.wps.WebProcessingService.
    Provides access to WPS GetCapabilities and Execute requests.

    """

    def __init__(self, url, username=None, password=None):
        """ Inits WebProcessingService """
        self._url = url

        self._service = WebProcessingService(
            url,
            username=username,
            password=password,
            verbose=False,
            skip_caps=True)

    def init(self):
        """ Executes WPS GetCapabilites request.

        Retrieves a servers description data (identification and provider)
        and its processes.

        """
        self._service.getcapabilities()

    @property
    def identification(self):
        """ Returns identification data as JSON. """
        if not self._service.identification:
            raise WPSClientError(
                'Verify %s is correct and WPS.init() was called.' %
                (self._url,))

        ident = self._service.identification

        return dict((x, getattr(ident, x)) for x in _IDENTIFICATION)

    @property
    def provider(self):
        """ Returns provider data as JSON. """
        if not self._service.provider:
            raise WPSClientError(
                'Verify %s is correct and WPS.init() was called.' %
                (self._url,))

        prov = self._service.provider

        prov_dict = dict((x, getattr(prov, x)) for x in _PROVIDER)

        contact = prov_dict['contact']

        prov_dict['contact'] = dict((x, getattr(contact, x)) for x in _CONTACT)

        return prov_dict

    def get_process(self, name):
        """ Returns process from name. """
        processes = [proc for proc in self._service.processes
                     if proc.identifier == name]

        if not len(processes):
            raise WPSClientError('No process named \'%s\' was found.' % (name,))

        return Process.from_identifier(self, processes[0].identifier)

    def execute(self, process_id, inputs, store=False, status=False):
        """ Formats data and executs WPS process. """
        input_list = [
            (key, value) for key, value in inputs.iteritems()
        ]

        # Unwraps self._service.execute since we may want to store execute
        # responses but not run async on the server side. Issue with 
        # Pywps==3.2.6 where status=True causes executing process to fork.
        execution = WPSExecution(version=self._service.version,
                                 url=self._service.url,
                                 username=self._service.username,
                                 password=self._service.password,
                                 verbose=self._service.verbose)

        request_element = execution.buildRequest(process_id, input_list, output='output')

        request_document = request_element.xpath(
            '/wps100:Execute/wps100:ResponseForm/wps100:ResponseDocument',
            namespaces=request_element.nsmap)[0]

        request_document.set('status', str(status))
        request_document.set('storeExecuteResponse', str(store))

        execution.request = etree.tostring(request_element)

        response = execution.submitRequest(execution.request) 

        execution.parseResponse(response)

        return execution

    def __iter__(self):
        for proc in self._service.processes:
            yield Process.from_identifier(self, proc.identifier)

    def __repr__(self):
        return 'WPS(url=%r, service=%r)' % (self._url, self._service)

    def __str__(self):
        return json.dumps({
            'identification': self.identification,
            'provider': self.provider},
                          indent=4)

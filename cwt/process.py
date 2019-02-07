"""
Process Module.
"""

import json
import logging 
import time
import datetime
import warnings

from cwt.parameter import Parameter

logger = logging.getLogger('cwt.process')

def input_output_to_dict(value):
    data = value.__dict__

    data['metadata'] = [x.__dict__ for x in data['metadata']]

    # Included from ComplexData
    try:
        data['defaultValue'] = data['defaultValue'].__dict__
    except KeyError:
        pass

    try:
        data['supportedValues'] = [x.__dict__ for x in data['supportedValues']]
    except KeyError:
        pass

    return data

class StatusTracker(object):
    def __init__(self, stale_threshold):
        self.history = {}
        self.start = None
        self.stale_threshold = stale_threshold

    @property
    def elapsed(self):
        elapsed = datetime.datetime.now() - self.start

        return elapsed.total_seconds()

    def update(self, message):
        now = datetime.datetime.now()

        if self.start is None:
            self.start = now

        self.history[message] = now

        print message

        logger.info(message)

class Process(Parameter):
    """ A WPS Process

    Wraps a WPS Process.

    Arguments:
        process: A DescribeProcessResponse object.
        name: A string name for the process to be used as the input of another process.
    """
    def __init__(self, process, name=None):
        super(Process, self).__init__(name)

        self.process = process

        self.context = None

        self.processed = False

        self.inputs = []

        self.parameters = {}

        self.domain = None

        self.status_tracker = None

        self._identifier = None
        self._title = None
        self._process_outputs = None
        self._data_inputs = None
        self._status_supported = None
        self._store_supported = None
        self._process_version = None
        self._abstract = None
        self._metadata = None

    def __repr__(self):
        return ('Process(identifier={!r}, title={!r}, status_supported={!r}, '
                'store_supported={!r}, process_version={!r}, abstract={!r}, '
                'metadata={!r})').format(self.identifier, self.title, self.status_supported,
                                        self.store_supported, self.process_version,
                                        self.abstract, self.metadata)

    @classmethod
    def from_owslib(cls, process):
        obj = cls(process)

        obj._identifier = process.identifier

        obj._title = process.title

        obj._process_outputs = [input_output_to_dict(x) 
                                for x in process.processOutputs]

        obj._data_inputs = [input_output_to_dict(x)
                            for x in process.dataInputs]

        obj._status_supported = process.statusSupported

        obj._store_supported = process.storeSupported

        obj._process_version = process.processVersion

        obj._abstract = process.abstract

        obj._metadata = [x.__dict__ for x in process.metadata]

        return obj

    @classmethod
    def from_dict(cls, data):
        """ Attempts to load a process from a dict. """
        obj = cls(name=data.get('result'))

        obj._identifier = data.get('name')

        obj.inputs = data.get('input', [])

        obj.domain = data.get('domain', None)

        known_keys = ('name', 'input', 'result')

        proc_params = {}

        for key in data.keys():
            if key not in known_keys:
                d = data.get(key)

                if isinstance(d, (dict)):
                    if key == 'gridder':
                        proc_params[key] = Gridder.from_dict(d)
                else:
                    proc_params[key] = NamedParameter.from_string(key, d)

        obj.parameters = proc_params

        return obj

    @property
    def identifier(self):
        return self._identifier

    @property
    def title(self):
        return self._title

    @property
    def process_outputs(self):
        return self._process_outputs

    @property
    def data_inputs(self):
        return self._data_inputs

    @property
    def status_supported(self):
        return self._status_supported

    @property
    def store_supported(self):
        return self._store_supported

    @property
    def process_version(self):
        self._process_version

    @property
    def abstract(self):
        return self._abstract

    @property
    def metadata(self):
        return self._metadata

    @property
    def processing(self):
        """ Checks if the process is still working.

        This will update the wrapper with the latest status and return
        True if the process is waiting or running.

        Returns:
            A boolean denoting whether the process is still working.
        """
        self.context.checkStatus(sleepSecs=0)

        return self.accepted or self.started

    @property
    def exception_dict(self):
        if self.errored:
            return [x.__dict__ for x in self.context.errors]

        return None

    @property
    def accepted(self):
        return self.check_context_status('ProcessAccepted')

    @property
    def started(self):
        return self.check_context_status('ProcessStarted')

    @property
    def paused(self):
        return self.check_context_status('ProcessPaused')

    @property
    def failed(self):
        return self.check_context_status('ProcessFailed')

    @property
    def succeeded(self):
        return self.check_context_status('ProcessSucceeded')

    @property
    def errored(self):
        return self.check_context_status('Exception')

    @property
    def output(self):
        """ Return the output of the process if done. """
        if not self.succeeded:
            raise CWTError('No output available process has not succeeded')

        # CWT only expects a single output in json format
        data = json.loads(self.context.processOutputs[0].data[0])

        if 'uri' in data:
            output_data = Variable.from_dict(data)
        elif 'outputs' in data:
            output_data = [Variable.from_dict(x) for x in data['outputs']]
        else:
            output_data = data

        return output_data

    @property
    def status(self):
        msg = None

        if self.accepted:
            msg = 'ProcessAccepted {!s}'.format(self.context.statusMessage)
        elif self.started:
            msg = 'ProcessStarted {!s} {!s}'.format(self.context.statusMessage, 
                                                    self.context.percentCompleted)
        elif self.paused:
            msg = 'ProcessPaused {!s} {!s}'.format(self.context.statusMessage,
                                                   self.context.percentCompleted)
        elif self.failed:
            msg = 'ProcessFailed {!s}'.format(self.context.statusMessage)
        elif self.succeeded:
            msg = 'ProcessSucceeded {!s}'.format(self.context.statusMessage)
        elif self.errored:
            exception_msg = '->'.join([x['text'] for x in self.exception_dict.values()])

            msg = 'Exception {!s}'.format(exception_msg)
        else:
            msg = 'Status unavailable'

        return msg

    def check_context_status(value):
        try:
            return self.context.status == value
        except AttributeError:
            raise CWTError('Process is missing a context')

    def wait(self, stale_threshold=None, timeout=None, sleep=None):
        if stale_threshold is None:
            stale_threshold = 4

        self.status_tracker = StatusTracker(stale_threshold)

        if sleep is None:
            sleep = 1.0

        self.status_tracker.update(self.status)

        while self.processing:
            self.status_tracker.update(self.status)

            time.sleep(sleep)

            if timeout is not None and self.status_tracker.elapsed > timeout:
                raise WPSError('Job has timed out after "{!s}" seconds', elapsed.total_seconds())

        self.status_tracker.update(self.status)

        return self.succeeded

    def validate(self):
        input_limit = None

        if self.metadata is None:
            return

        if 'inputs' in self.metadata:
            if self.metadata['inputs'] != '*':
                input_limit = int(self.metadata['inputs'])

        if input_limit is not None and len(self.inputs) > input_limit:
            raise ValidationError('Invalid number of inputs, expected "{}", got "{}"', input_limit, len(self.inputs))
        
    def set_domain(self, domain):
        self.domain = domain

    def get_parameter(self, name, required=False):
        """ Retrieves a parameter

        Args:
            name: A string name of the parameter.
            required: A boolean flag denoting whether the parameter is required.

        Returns:
            A NamedParameter object.

        Raises:
            Exception: The parameter is required and not present.
        """
        if name not in self.parameters and required:
            raise ProcessError('Parameter {} is required but not present', name)

        return self.parameters.get(name, None)

    def add_parameters(self, *args, **kwargs):
        """ Add a parameter.

        kwargs can contain two formats.

        k=v where v is a NamedParameter
        
        Args:
            args: A list of NamedParameter objects.
            kwargs: A dict of NamedParameter objects or k=v where k is the name and v is string.
        """
        for a in args:
            if not isinstance(a, NamedParameter):
                raise ProcessError('Invalid parameter type "{}", should be a NamedParameter', type(a))

            self.parameters[a.name] = a

        for k, v in kwargs.iteritems():
            if not isinstance(v, (tuple, list)):
                v = [v]

            self.parameters[k] = NamedParameter(k, *v)

    def add_inputs(self, *args):
        """ Set the inputs of the Process. 
        
        Args:
            args: A list of Process/Variable objects.
        """
        self.inputs.extend(args)

    def resolve_inputs(self, inputs, operations):
        """ Attempts to resolve the process inputs.

        Resolves the processes inputs from strings to Process/Variable objects.

        Args:
            inputs: A dict of Variables where the key is name.
            operations: A dict of Processes where the key is name.

        """
        logger.info('Proccess {} resolving inputs {}'.format(self.identifier, self.inputs))

        temp = dict((x, None) for x in self.inputs)

        for key in temp.keys():
            if key in inputs:
                temp[key] = inputs[key]
            elif key in operations:
                if operations[key].processed:
                    raise ProcessError('Found circular loop in execution tree')

                temp[key] = operations[key]

                temp[key].processed = True

                temp[key].resolve_inputs(inputs, operations)
            else:
                raise ProcessError('Input "{}" not found', key)

        self.inputs = temp.values()

    def collect_input_processes(self, processes=None, inputs=None):
        """ Aggregates the process trees inputs.

        A DFS to collect the trees inputs into two lists, Operations and Variables.

        Args:
            processes: A list of current processes discovered.
            inputs: A list of Process/Variables to processes.

        Returns:
            A two lists, one of Processes and the other of Variables.
        """

        if processes is None:
            processes = []

        if inputs is None:
            inputs = {}

        new_processes = [x for x in self.inputs if isinstance(x, Process)]

        inputs.update(dict((x.name, x) for x in self.inputs
                           if isinstance(x, Variable)))

        for p in new_processes:
            p.collect_input_processes(processes, inputs)

        processes.extend(new_processes)

        return processes, inputs.values()

    def update_status(self):
        """ Retrieves the latest process status. """
        if self.response is None or self.response.statusLocation is None:
            return None

        response = self.__client.http_request('GET', self.response.statusLocation, {}, {}, {})

        self.response = wps.CreateFromDocument(response)

    def to_dict(self):
        """ Returns a dictionary representation."""
        data = {
            'name': self.identifier,
            'result': self.name
        }

        if self.domain is not None:
            try:
                params['domain'] = self.domain.name
            except AttributeError:
                params['domain'] = self.domain

        inputs = []

        for i in self.inputs:
            try:
                inputs.append(i.name)
            except AttributeError:
                inputs.append(i)

        data['input'] = inputs

        if len(self.parameters) > 0:
            for name, value in self.parameters.iteritems():
                data[name] = value.to_dict()

        return data

    def parameterize(self):
        """ Create a dictionary representation of the Process. """
        warnings.warn('parameterize is deprecated, use to_dict instead',
                      DeprecationWarning)

        return self.to_dict()

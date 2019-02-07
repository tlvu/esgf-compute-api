"""
Domain Module.
"""

import warnings

from dimension import Dimension
from parameter import Parameter

class Domain(Parameter):
    """ Domain.

    A domain consist of one or more dimensions. A mask can be associated with
    a domain, further construing the domain being represented.

    Simple domain.

    >>> domain = Domain([Dimesnion('lat', 90, -90, Dimension.values)])

    Domain with a mask.

    >>> domain = Domain([
            Dimension('lat', 90, -90, Dimension.values, name='lat'),
            Dimension('lon', 0, 90, Dimension.values, name='lon'),
        ],
        mask = Mask('http://thredds/clt.nc', 'clt', 'var_data<0.5'))

    Attributes:
        dimensions: List of Dimensions.
        mask: Mask to be applied to the domain.
        name: Name of the domain.
    """
    def __init__(self, dimensions=None, mask=None, name=None, **kwargs):
        """ Domain init. """
        super(Domain, self).__init__(name)

        self.mask = mask

        self.dimensions = {}

        if dimensions is not None:
            for dim in dimensions:
                self.dimensions[dim.name] = dim

        for name, value in kwargs.iteritems():
            self.add_dimension(name, value)

    @classmethod
    def from_dict(cls, data):
        """ Creates domain from dict reperesentation. """
        blacklist = ['id', 'mask']


        try:
            name = data['id']
        except KeyError as e:
            raise MissingRequiredKeyError(e)

        dimensions = []

        for key, value in data.iteritems():
            if key not in blacklist:
                dimensions.append(Dimension.from_dict(value, key))

        try:
            mask_data = Mask.from_dict(data['mask'])
        except KeyError as e:
            raise MissingRequiredKeyError(e)
        except:
            mask_data = None

        return cls(dimensions=dimensions, mask=mask_data, name=name)

    def add_dimension(self, name, value):
        if name in self.dimensions:
            raise CWTError('Dimensions {!r} already exists', name)

        if isinstance(value, slice):
            args = [name, value.start, value.stop, INDICES, value.step]
        elif isinstance(value, (list, tuple)):
            if len(value) < 2:
                raise WPSError('Must provide a minimum of two values (start, stop) for dimension "{dim}"', dim=name)

            if len(value) > 2:
                step = value[3]
            else:
                step = 1

            if all(isinstance(x, (float, int)) for x in value[:2]):
                crs = VALUES
            elif all(isinstance(x, str) for x in value[:2]):
                crs = TIMESTAMPS
            else:
                raise WPSError('Could not determin dimension crs')

            args = [name, value[0], value[1], crs, step]
        else:
            raise WPSError('Dimension\'s value cannot be of type "{type}"', type=type(value))

        self.dimensions[name] = Dimension(*args)

    def get_dimension(self, names):
        if not isinstance(names, (list, tuple)):
            names = [names]

        for dim in self.dimensions:
            if dim.name in names:
                return dim

        return None

    def to_dict(self):
        """ Returns a dictionary representation."""
        data = {
            'id': self.name
        }

        for name, value in self.dimensions.iteritems():
            data[name] = value.to_dict()

        if self.mask is not None:
            data['mask'] = self.mask.to_dict()

        return data

    def parameterize(self):
        """ Returns parameter for GET request. """
        warnings.warn('parameterize is deprecated, use to_dict instead',
                      DeprecationWarning)

        return self.to_dict()

    def __repr__(self):
        return 'Domain(dimensions=%r, mask=%r, name=%r)'.format(
            self.dimensions, self.mask, self.name)

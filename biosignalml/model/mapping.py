######################################################
#
#  BioSignalML Management in Python
#
#  Copyright (c) 2010-2013  David Brooks
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
######################################################

"""
Map attribute values to and from RDF.

Mappings are specified via dictionaries when creating :class:`Mapping` classes.

A stream of RDF statements for an :class:`~biosignalml.model.core.AbstractObject`
can then be generated by calling :meth:`Mapping.statement_stream`; values to assign
to attributes of an object are obtained from RDF by using :meth:`Mapping.metadata`
and :meth:`Mapping.get_value_from_graph`.

"""


import os
import logging
from collections import namedtuple

from biosignalml.rdf import Node, Uri, Resource, Literal, Statement, XSD

__all__ = [ 'PropertyMap', 'Mapping' ]


URI_SCHEMES = [ 'http', 'file' ]

datatypes = { XSD.float:              float,
              XSD.double:             float,
              XSD.integer:            long,
              XSD.long:               long,
              XSD.int:                int,
              XSD.short:              int,
              XSD.byte:               int,
              XSD.nonPostiveInteger:  long,
              XSD.nonNegativeInteger: long,
              XSD.positiveInteger:    long,
              XSD.negativeInteger:    long,
              XSD.unsignedLong:       long,
              XSD.unsignedInt:        long,
              XSD.unsignedShort:      int,
              XSD.unsignedByte:       int,
            }


class PropertyMap(object):
#=========================

  """
  Details of how to map attribute values to and from RDF.

  :param property: The property to use in a RDF statement giving
    an attribute's value.
  :type property: :class:`~biosignalml.rdf.Resource`
  :param datatype: The optional datatype for a RDF literal value.
  :type datatype: :class:`~biosignalml.rdf.Resource`
  :param to_rdf: An optional function to convert from an attribute's value
    to the object for a RDF statement,
  :param to_rdf: An optional function to convert from the object for a RDF
    statement to an attribute value.
  :param bool subelement: If True, AbstractObjects referenced by properties
    are recursively output when generating RDF statements.
  :param bool functional: Set False if the property can have multiple values.
    Default is True.
  """
  def __init__(self, property, datatype=None, to_rdf=None, from_rdf=None, subelement=False, functional=True):
  #---------------------------------------------------------------------------------------------------------
    self.property = property
    self.datatype = datatype
    self.to_rdf = to_rdf
    self.from_rdf = from_rdf
    self.subelement = subelement
    self.functional = functional

  @staticmethod
  def get_uri(v):
  #--------------
    '''
    Get the `uri` attribute if it exists, otherwise the object as a string.
    '''
    return v.uri if hasattr(v, 'uri') else Uri(v)


ReverseEntry = namedtuple('ReverseEntry', 'attribute, datatype, from_rdf, functional')
#===========
"""
A reverse mapping, from RDF to an attribute.

Reverse maps are created from :class:`PropertyMap`\s when :class:`Mapping` classes
are created and updated.
"""

class Mapping(object):
#=====================

  """
  Map attribute values to and from RDF.

  :param metaclass: A mapping dictionary.
  :param usermap: A mapping dictionary.
  :type usermap: dict

  A mapping dictionary has has 2-tuples as keys, indexing :class:`PropertyMap`\s.

  The first element of a key is either None, meaning the map is for all attributes
  having the name, or is a :class:`~biosignalml.rdf.Resource`, meaning the map is
  only for attributes of :class:`~biosignalml.model.core.AbstractObject`\s that
  have the Resource as their :attr:`~biosignalml.model.core.AbstractObject.metaclass`.

  The second element of a key is a string with the name of the attribute which the
  PropertyMap is for.

  """
  def __init__(self, metaclass=None, usermap=None):
  #------------------------------------------------
    self.mapping = { }        #: The mapping dictionary to convert to RDF.
    self.reversemap = { }     #: The reverse mapping from RDF.
    if usermap is not None: self.update(metaclass, usermap)

  def update(self, metaclass, usermap):
  #------------------------------------
    """
    Update a mapping.

    :param usermap: A mapping dictionary.
    :type usermap: dict
    """
    for k, v in usermap.iteritems(): self.mapping[(metaclass, k)] = v
    self.reversemap = { (k[0], str(m.property)): ReverseEntry(k[1], m.datatype, m.from_rdf, m.functional)
                          for k, m in self.mapping.iteritems() }

  @staticmethod
  def _makenode(value, dtype, mapfn):
  #----------------------------------
    if   isinstance(value, Node) and value.is_resource(): return value
    elif isinstance(value, Uri): return Resource(value)
    elif hasattr(value, 'node'): return value.node
    elif hasattr(value, 'uri') and mapfn in [None, PropertyMap.get_uri]:
      if isinstance(value.uri, Node): return value.uri
      else:                           return Resource(value.uri)
    else:
      if mapfn:
        try: value = mapfn(value)
        except Exception, msg:
          logging.error("Exception mapping literal with '%s': %s", str(mapfn), msg)
      value = unicode(value)
      if len(value.split(':')) > 1 and value.split(':')[0] in URI_SCHEMES:
        return Resource(value)
      else:
        return Literal(value, datatype=dtype)

  def _statements(self, subject, map, value):
  #------------------------------------------
    from .core import AbstractObject
    if value not in [None, '']:
      if hasattr(value, '__iter__'):
        for v in value:
          if isinstance(v, AbstractObject):
            yield Statement(subject, map.property, self._makenode(v, None, None))
            if map.subelement:
              for s in v.metadata_as_stream(): yield s
          else:
            yield Statement(subject, map.property, self._makenode(v, map.datatype, map.to_rdf))
      elif isinstance(value, AbstractObject) and map.to_rdf in [None, PropertyMap.get_uri]:
        yield Statement(subject, map.property, self._makenode(value, None, None))
        if map.subelement:
          for s in value.metadata_as_stream(): yield s
      else:
        yield Statement(subject, map.property, self._makenode(value, map.datatype, map.to_rdf))

  def statement_stream(self, resource):
  #------------------------------------
    """
    Generate :class:`Statement`\s from a resource's attributes and
    elements in its `metadata` dictionary.

    :param resource: An object with ``metaclass`` attributes on
      some of its classes.
    :type resource: :class:`~biosignalml.model.core.AbstractObject`

    All attributes defined in the mapping table are tested to see if they are defined for
    the resource, and if so, their value in the resource is translated to an object node
    in a RDF statement.
    """
    if hasattr(resource, 'node'):
      subject = resource.node
      metaclasses = [ c.metaclass for c in resource.__class__.__mro__ if c.__dict__.get('metaclass') ]
      metadict = getattr(resource, 'metadata', { })
      for k, m in self.mapping.iteritems():
        if k[0] is None or k[0] in metaclasses:  ## Or do we need str() before lookup ??
          for s in self._statements(subject, m, getattr(resource, k[1], None)): yield s
          for s in self._statements(subject, m, metadict.get(k[1], None)): yield s

  @staticmethod
  def _makevalue(node, dtype, from_rdf):
  #-------------------------------------
    if node is None: return None
    elif node.is_resource(): v = Uri(node.uri)
    elif node.is_blank(): v = node.blank
    elif node.is_literal():
      v = node.value
      if dtype: v = datatypes.get(dtype, str)(v)
    else: v = str(node)
    return from_rdf(v) if from_rdf else v

  def metadata(self, metaclass, statement):
  #----------------------------------------
    """
    Given a RDF statement and a metaclass, lookup the statement's predicate
    in the reverse mapping table and use its properties to translate the value of the
    statement's object.

    :rtype: tuple(Uri, attribute, value, functional) where the ``Uri`` is of the statement's
      subject; ``attribute`` is a string with the Python name of an attribute; ``value`` is
      the Python value for the attribute; and ``functional`` is True if the attribute can
      only have a single value.

    """
    m = self.reversemap.get((metaclass, str(statement.predicate.uri)), None)
    if m is None: m = self.reversemap.get((None, str(statement.predicate.uri)), ReverseEntry(None, None, None, None))
    return (statement.subject.uri, m.attribute, self._makevalue(statement.object, m.datatype, m.from_rdf), m.functional)

  def get_value_from_graph(self, resource, attr, graph):
  #-----------------------------------------------------
    """
    Find the property corresponding to a resource's attribute and if a statement
    about the resource using the property is in the graph, translate and return
    its object's value.
    """
    m = self.mapping.get((resource.metaclass, attr), None)
    if m is None: m = self.mapping.get((None, attr))
    if m:
      return self._makevalue(graph.get_object(resource.uri, m.property), m.datatype, m.from_rdf)


if __name__ == '__main__':
#=========================

  from biosignalml import Recording, Annotation
  import biosignalml.rdf as rdf

  #logging.basicConfig(level=logging.DEBUG)

  class MyRecording(Recording):
  #----------------------------
    mapping = { 'xx': PropertyMap(rdf.DCT.subject),
                'yy': PropertyMap('http://example.org/onto#subject'),
                'zz': PropertyMap('http://example.org/onto#annotation'),
     }


  r = MyRecording('http://example.org/uri1', description='Hello', yy = ['subject', 'in', 'list'] )
  g = rdf.Graph()
  r.save_to_graph(g)

  s = MyRecording.create_from_graph('http://example.org/uri1', g)
  assert(r.metadata_as_string(rdf.Format.TURTLE) == s.metadata_as_string(rdf.Format.TURTLE))
  s.comment='From graph'

  user = 'http://example.org/users/test-user'

  a1 = 'http://example.org/annotation/1'
  a2 = 'http://example.org/annotation/2'
  a3 = 'http://example.org/annotation/3'

  t1 = 'http://example.org/onto#tag1'
  t2 = 'http://example.org/onto#tag2'
  t3 = 'http://example.org/onto#tag3'
  a = Annotation.Note(a1, s.uri, user, 'A test recording...')
  b = Annotation.Tag(a2, s.uri, user, t1)
  c = Annotation(a3, s.uri, user, tags=[t2, t3], text='Multiple tags')

  #print a.metadata_as_string(rdf.Format.TURTLE)
  #print b.metadata_as_string(rdf.Format.TURTLE)
  #print c.metadata_as_string(rdf.Format.TURTLE)

  c.save_to_graph(g)
  d = Annotation.create_from_graph(a3, g)
  assert(c.metadata_as_string(rdf.Format.TURTLE) == d.metadata_as_string(rdf.Format.TURTLE))

  s.metadata['zz'] = [ a, b, c ]
  print s.metadata_as_string(rdf.Format.TURTLE)


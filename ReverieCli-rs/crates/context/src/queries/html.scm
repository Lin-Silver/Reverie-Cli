(element
  [(start_tag (attribute (attribute_name) @_attribute (quoted_attribute_value (attribute_value) @name)))
   (self_closing_tag (attribute (attribute_name) @_attribute (quoted_attribute_value (attribute_value) @name)))]
  (#eq? @_attribute "id")) @definition.property

(class_name_statement name: (name) @name) @definition.class
(class_definition name: (name) @name) @definition.class
(function_definition name: (name) @name) @definition.method
(variable_statement name: (name) @name) @definition.variable
(export_variable_statement name: (name) @name) @definition.variable
(onready_variable_statement name: (name) @name) @definition.variable
(const_statement name: (name) @name) @definition.constant
(signal_statement name: (name) @name) @definition.property
(call (identifier) @name) @reference.call
(attribute_call (identifier) @name) @reference.call
(extends_statement (type) @name) @reference.implementation

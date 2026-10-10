"""Parse CloudFormation YAML without executing arbitrary YAML constructors."""
import yaml

class CloudFormationLoader(yaml.SafeLoader):
    pass

def construct_intrinsic(loader, tag, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {tag if tag in ('Ref', 'Condition') else 'Fn::' + tag: value}

CloudFormationLoader.add_multi_constructor('!', construct_intrinsic)

def load_template(text):
    result = yaml.load(text, Loader=CloudFormationLoader)
    if not isinstance(result, dict) or not isinstance(result.get('Resources'), dict):
        raise ValueError('Invalid CloudFormation template')
    return result

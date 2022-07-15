import yaml


def load_model_config():
    with open("model_config.yml") as config_file:
    		# It was yaml.load and we had to change it to yaml.safe_load
        model_config = yaml.safe_load(config_file)
        # Todo: check_model_config(model_config)

    return model_config

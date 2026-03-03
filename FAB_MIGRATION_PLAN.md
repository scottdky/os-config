# Fabric Migration Plan to Cmd Manager

> Historical planning document. Some items reflect early migration ideas and may not match the current implementation.
> For current usage, see `README.md` and `MIGRATION_GUIDE.md`.

## Structure
- lib: various OS and file operations
- core: some basic server ops
- plugins: custom server ops

### Core & Plugin Structure
Both core and plugin dirs will have the same structure
- resources
- python ops
- config.yaml

## Operation
- Each op file will have a main that allows it to run as a standalone script
- The core and plugin dirs will each have a config.yaml file. The plugin config file will augment or override the core one as needed

## Config yaml file
This will consist of a menu section and config section for each op.

## Repos
The GitLab repo will be public in order to be open source and give back. It will also be mirrored to GitHub to increase visibility.

## Plugin Sources
The plugin folder will be empty in this repo. They can be added in one of the following ways:
1. **Not recommended**: Simply copy them in. "$ git clean" will delete them.
2. Symlink to them. In plugin dir, run $ ln -s PATH_TO_PLUGINS myplugins
3. Copy `config_example.yaml` to your local config file and in it add the following:
   PLUGINS
   - PATH_TO_PLUGINS

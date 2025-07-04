# Convai Modding Tool

## Overview
A tool that automates the setup and management of Unreal Engine projects for Convai integration. It creates new modding projects or updates existing ones with required plugins, configurations, and assets.

## Features
- **Create Mode**: Sets up a new Unreal Engine project with Convai plugins and dependencies
- **Update Mode**: Updates existing modding projects with latest Convai components
- Automatically downloads and installs required plugins from GitHub and Google Drive
- Configures project settings and API keys
- Supports both Scene and Avatar asset types (including MetaHuman)

## Requirements
- Unreal Engine 5.5
- Cross-compilation toolchain (v23_clang-18.1.0-rockylinux8)
- Python 3.6+
- Internet connection for downloading dependencies

## Usage

### Run the Tool
```bash
python ConvaiModdingTool.py
```

### Follow the Prompts
1. Choose **Create** (new project) or **Update** (existing project)
2. Enter Unreal Engine installation path
3. For new projects: Enter project name, API key, and asset type
4. For updates: Select existing project to update

The tool will automatically:
- Download required plugins (ConvAI, ConvaiHTTP, ConvaiPakManager, etc.)
- Configure project settings and INI files
- Set up content based on asset type selection
- Build the project

## Project Structure
```
YourProject/
├── Content/           # Project content
├── Plugins/           # Installed Convai plugins
├── Config/            # Configuration files
└── ConvaiEssentials/  # Downloaded dependencies and metadata
``` 
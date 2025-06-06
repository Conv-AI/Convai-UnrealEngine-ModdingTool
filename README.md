# **Convai Modding Tool - Unreal Engine Project Setup Guide**

## **Overview**
The Convai Modding Tool automates the setup of an Unreal Engine project by generating a unique project name, creating a project from a template, installing required plugins, and building the project using UnrealBuildTool.

---

## **How the Script Works**

### **1. Generating Project and Plugin Names**
- The script generates unique identifiers using `uuid4`, then processes them into Unreal-compatible names using `trim_unique_str()`.
- The result is a **20-character uppercase-only alphanumeric string** that starts with a letter.

### **2. Retrieving Unreal Engine Path**
- If not passed as a command-line argument, the script prompts the user to enter the Unreal Engine installation directory.
- This path is used to locate the default template and version info.

### **3. Extracting and Validating the Engine Version**
- It reads the installed version from `Version.h` and checks if it's supported using `is_supported_engine_version()`.
- Currently, only **Unreal Engine 5.3** is supported.

### **4. Creating the Project Structure**
- Copies the `TP_Blank` template from the engine to a new directory.
- Updates all filenames and internal references from `TP_Blank` to the generated project name.
- Ensures the engine version is set inside the `.uproject` file using `set_engine_version()`.

### **5. Creating a Content-Only Plugin**
- A content-only plugin is generated using `create_content_only_plugin()`.
- This plugin:
  - Has no source code (just a `Content/` folder).
  - Is registered in the `.uproject` file.
  - Uses a minimal `.uplugin` file with metadata like `FriendlyName`, `CanContainContent: true`, etc.

### **6. Downloading Additional Plugins**
- Uses `gdown` to download plugin ZIPs from a Google Drive folder.
- Plugins are extracted to the `Plugins/` directory automatically via `download_plugins_from_gdrive_folder()`.

### **7. Enabling Required Plugins**
- Plugins listed in the script (`ConvAI`, `ConvaiHTTP`, `ConvaiPakManager`, `JsonBlueprintUtilities`, and the generated one) are enabled in the `.uproject` file using `enable_plugin_in_uproject()`.

### **8. Compiling the Project**
- Executes `UnrealBuildTool.exe` to build the project.
- If the build fails, an error is shown.

---

## **How to Use the Script**

### **Prerequisites**
- Unreal Engine **5.3** installed.
- Python **3.6+** installed if running in source mode.
- Internet connection to download plugins from Google Drive.

### **Run Options**

#### **Option 1: Run as Python Script**
```sh
python ConvaiModdingTool.py /path/to/Unreal/Engine

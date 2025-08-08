# MuseTalk Server Startup Fixes

## Issues Fixed

### 1. Conda Activation Error on Remote Servers
**Problem**: The original `start_servers.py` used `conda activate` which requires `conda init` to be run first, causing errors on remote servers.

**Solution**: 
- Replaced `conda activate` with direct Python executable path detection
- Added fallback to `conda run` which works better on remote servers
- Improved error handling and logging

### 2. Hardcoded Port Numbers
**Problem**: Port numbers were hardcoded and didn't respect user configuration from `create_env.py`.

**Solution**:
- Now properly loads environment variables from `.env` file
- Passes environment variables to both servers
- Uses the same configuration system as `create_env.py`

## How to Use

### 1. Configure Your Environment
First, run the configuration script to set up your ports and host settings:

```bash
python create_env.py
```

This will create a `.env` file with your custom settings.

### 2. Start the Servers
Run the updated startup script:

```bash
python start_servers.py
```

The script will:
- Load configuration from `.env` file
- Check if the MuseTestEnv conda environment exists
- Start the MuseTalk inference server in the conda environment
- Start the web interface server
- Display proper error messages if something goes wrong

## Testing

### Test Environment Variable Loading
```bash
python test_env_loading.py
```

### Test Conda Environment Detection
```bash
python test_conda_env.py
```

## Key Improvements

1. **Better Error Handling**: More detailed error messages and proper exception handling
2. **Cross-Platform Support**: Works on Windows, Linux, and macOS
3. **Remote Server Support**: Uses `conda run` as fallback for remote servers
4. **Configuration Respect**: Properly uses user configuration from `.env` file
5. **Environment Variable Passing**: Ensures both servers receive the correct configuration

## Troubleshooting

### If you get conda-related errors:
1. Make sure the MuseTestEnv environment exists: `conda env list`
2. If it doesn't exist, create it: `conda env create -f environment.yml`
3. Run the test script: `python test_conda_env.py`

### If ports are not working:
1. Check your `.env` file exists and has correct values
2. Run the test script: `python test_env_loading.py`
3. Make sure the ports are not already in use

### For remote access:
1. Run `python create_env.py` and choose "y" for remote access
2. This will set hosts to "0.0.0.0" instead of "localhost"
3. Make sure your firewall allows connections to the specified ports

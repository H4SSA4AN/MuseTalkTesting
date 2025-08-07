# Environment Configuration

This document explains how to configure MuseTalk using environment variables to customize port numbers and other settings.

## Quick Setup

### Option 1: Interactive Configuration (Recommended)
Run the interactive configuration script:
```bash
python create_env.py
```

This will guide you through setting up your `.env` file with custom port numbers.

### Option 2: Manual Configuration
1. Copy the example environment file:
   ```bash
   cp env_example.txt .env
   ```

2. Edit the `.env` file with your preferred settings:
   ```bash
   # MuseTalk inference server settings
   MUSETALK_HOST=localhost
   MUSETALK_PORT=8081
   
   # Web interface server settings
   WEB_HOST=localhost
   WEB_PORT=8080
   ```

## Environment Variables

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MUSETALK_HOST` | `localhost` | Host for MuseTalk inference server |
| `MUSETALK_PORT` | `8081` | Port for MuseTalk inference server |
| `WEB_HOST` | `localhost` | Host for web interface server |
| `WEB_PORT` | `8080` | Port for web interface server |

### Remote Access Configuration

To enable remote access (accessing from other machines), set the hosts to `0.0.0.0`:

```bash
# For remote access
MUSETALK_HOST=0.0.0.0
WEB_HOST=0.0.0.0
```

**Security Note**: When using `0.0.0.0`, ensure your firewall is properly configured to restrict access to trusted networks.

## Usage Examples

### Example 1: Custom Port Numbers
```bash
# .env file
MUSETALK_PORT=9001
WEB_PORT=9000
```

### Example 2: Remote Access with Custom Ports
```bash
# .env file
MUSETALK_HOST=0.0.0.0
MUSETALK_PORT=9001
WEB_HOST=0.0.0.0
WEB_PORT=9000
```

### Example 3: Local Development with Different Ports
```bash
# .env file
MUSETALK_PORT=8082
WEB_PORT=8083
```

## Starting Servers with Environment Variables

The startup scripts automatically load environment variables from the `.env` file:

### Python Script
```bash
python start_servers.py
```

### Linux/Mac Shell Script
```bash
chmod +x start_servers.sh
./start_servers.sh
```

### Windows Batch Script
```bash
start_servers.bat
```

## Testing with Environment Variables

All test scripts automatically use the configured environment variables:

```bash
# Debug server state
python debug_state.py

# Test inference restart
python test_inference_restart.py

# Test settings API
python test_settings_api.py
```

## Troubleshooting

### Port Already in Use
If you get a "port already in use" error:

1. Check what's using the port:
   ```bash
   # Linux/Mac
   lsof -i :8081
   
   # Windows
   netstat -ano | findstr :8081
   ```

2. Change the port in your `.env` file:
   ```bash
   MUSETALK_PORT=8082
   ```

### Environment Variables Not Loading
1. Ensure the `.env` file is in the project root directory
2. Check that the `.env` file has the correct format (no spaces around `=`)
3. Verify the file is not corrupted

### Firewall Configuration
When using custom ports, update your firewall rules:

```bash
# Ubuntu/Debian
sudo ufw allow 9000
sudo ufw allow 9001

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=9000/tcp
sudo firewall-cmd --permanent --add-port=9001/tcp
sudo firewall-cmd --reload
```

## File Structure

```
MuseTalkTesting-1/
├── .env                    # Your environment configuration (create this)
├── env_example.txt         # Example environment file
├── create_env.py           # Interactive configuration script
├── start_servers.py        # Python startup script
├── start_servers.sh        # Linux/Mac startup script
├── start_servers.bat       # Windows startup script
├── musetalkServer/
│   └── config.py           # Server configuration (uses env vars)
└── webrtc/
    └── config.py           # Web interface configuration (uses env vars)
```

## Best Practices

1. **Never commit `.env` files** to version control (they're already in `.gitignore`)
2. **Use different ports** for different environments (development, staging, production)
3. **Document your configuration** for team members
4. **Test port availability** before deploying
5. **Use descriptive port numbers** (e.g., 9001 for MuseTalk, 9000 for web interface)

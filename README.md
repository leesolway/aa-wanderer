# aa-wanderer

[Alliance Auth](https://gitlab.com/allianceauth/allianceauth) application interfacing your auth with a [wanderer](https://wanderer.ltd/) instance.

**Currently, in active development. Use at your own risks**

Big shoutout to A-A-Ron for his work on [allianceauth-multiverse](https://github.com/Solar-Helix-Independent-Transport/allianceauth-discord-multiverse) without which I wouldn't have been able to have multiple services.

## Planned features
- [ ] Wanderer ACL management through the auth
- [ ] Automated pings when a marked system is connected to the home hole

## Installation

### Step 1 - Check prerequisites

1. aa-wanderer is a plugin for Alliance Auth. If you don't have Alliance Auth running already, please install it first before proceeding. (see the official [AA installation guide](https://allianceauth.readthedocs.io/en/latest/installation/auth/allianceauth/) for details)
2. You need to have a map with administrator access on wanderer to recover the API key

### Step 2 - Install app

Make sure you are in the virtual environment (venv) of your Alliance Auth installation. Then install the newest release from PyPI:

```bash
pip install aa-wanderer
```

### Step 3 - Configure Auth settings

Configure your Auth settings (`local.py`) as follows:

- Add `'wanderer'` to `INSTALLED_APPS`
- Add below lines to your settings file:

```python
CELERYBEAT_SCHEDULE['wanderer_cleanup_access_lists'] = {
    'task': 'wanderer.tasks.cleanup_all_acess_lists',
    'schedule': crontab(minute='0', hour='*/1'),
}
```

Optional: Alter the application settings.
The list can be found in [Settings](#settings)

### Step 4 - Finalize App installation

Run migrations & copy static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

Restart your supervisor services for Auth.

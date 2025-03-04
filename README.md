# aa-wanderer

[Alliance Auth](https://gitlab.com/allianceauth/allianceauth) application linking your auth with a [wanderer](https://wanderer.ltd/) instance.

**Currently, in active development. Use at your own risks**

Big shoutout to A-A-Ron for his work on [allianceauth-multiverse](https://github.com/Solar-Helix-Independent-Transport/allianceauth-discord-multiverse) without which I wouldn't have been able to have multiple services.

## Planned features
- [ ] Wanderer ACL management through the auth
- [ ] Automated pings when a marked system is connected to the home hole

## Usage
Currently, I recommend keeping a normal wanderer access list on your map that you configure yourself.
You can add your corporation/alliance on this access list to make sure that all mains can easily open your map.
It also allows you to add another group if needed during a joint op. \
The application will create another access list that will be fully managed and shouldn't be manually edited.

## Installation

### Step 1 - Check prerequisites

1. aa-wanderer is a plugin for Alliance Auth. If you don't have Alliance Auth running already, please install it first before proceeding. (see the official [AA installation guide](https://allianceauth.readthedocs.io/en/latest/installation/auth/allianceauth/) for details)
2. You need to have a map with administrator access on wanderer to recover the map API key that will be used to create a new access list.

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
    'task': 'wanderer.tasks.cleanup_all_access_lists',
    'schedule': crontab(minute='0', hour='*/1'),
}
```

### Step 4 - Finalize App installation

Run migrations & copy static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

Restart your supervisor services for Auth.


### Commands

The following commands can be used when running the module:

| Name                    | Description                                                                              |
|-------------------------|------------------------------------------------------------------------------------------|
| `wanderer_cleanup_acls` | Will execute the cleanup command on all your managed maps and update their access lists. |

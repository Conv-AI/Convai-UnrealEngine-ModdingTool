"""Self-checks for the command bridge: no network, no display, no Unreal Engine.

Plain asserts, run with `python tests/test_bridge.py`. The flows are stand-ins that log
the lines the real ones log, which is the only thing the bridge infers anything from.
"""

import json
import logging
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_manager import RemoteConfig, config

# Seeded before anything reads it: a load() would go to GitHub.
config._remote_config = RemoteConfig(
    config={},
    version_data={'current-ue-version': '5.6', 'target-ue-version': '5.8',
                  'modding-tool-version': '9.9.9'},
    uploader_config={},
)

from bridge import dispatcher as dispatcher_module
from bridge.dispatcher import Dispatcher
from bridge.protocol import (CREATE_STEPS, MIGRATE_STEPS, REBUILD_STEPS, UPDATE_STEPS,
                             error, event, match_step,
                             parse_command, project_view, reply, step_from_line, step_marks,
                             step_titles)
from core.input_manager import InputManager
from core.logger import logger
from core.unreal_engine_manager import UnrealEngineManager

# The tool's logger writes emoji a cp1252 console cannot encode, and every test needs it
# enabled rather than disabled -- a disabled logger reaches no handler, and the queue
# handler is half of what is under test. The null handler keeps logging's own
# last-resort printer off stderr.
logger.logger.handlers.clear()
logger.logger.addHandler(logging.NullHandler())

ENGINE = "C:\\UE_5.6"
API_KEY = "secret-key-12345"


def make_project(root, name='MyScene_01', engine='5.6'):
    """A project the scan can read: metadata, and a .uproject named after it."""
    project_dir = os.path.join(root, name)
    essentials = os.path.join(project_dir, 'ConvaiEssentials')
    os.makedirs(essentials)
    with open(os.path.join(essentials, 'ModdingMetaData.txt'), 'w', encoding='utf-8') as handle:
        json.dump({'project_name': name, 'asset_type': 'Scene', 'api_key': 'project-key-abc',
                   'plugin_name': 'pl'}, handle)
    with open(os.path.join(project_dir, f'{name}.uproject'), 'w', encoding='utf-8') as handle:
        json.dump({'EngineAssociation': engine}, handle)
    return project_dir


def make_dispatcher(root, flows=None, signed_in=True, **kwargs):
    events = []
    bridge = Dispatcher('3.0.6', InputManager(root),
                        flows or {name: (lambda: None) for name in ('create', 'update', 'migrate')},
                        events.append, **kwargs)
    # A self-check must not read or write the developer's real session file.
    bridge.account.path = __import__('pathlib').Path(os.path.join(root, 'session.json'))
    if signed_in:
        bridge.account.adopt(API_KEY, 'Alex Chen', 'alex@example.com')
    return bridge, events


def call(bridge, command, **params):
    return bridge.handle({'id': f'c-{command}', 'command': command, 'params': params})


def data(answer):
    assert answer['ok'], answer
    return answer['data']


def failure(answer, code):
    assert not answer['ok'], answer
    assert answer['error']['code'] == code, answer['error']
    assert answer['error']['message'].strip(), answer['error']
    return answer['error']


def wait_for(events, name, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for envelope in list(events):
            if envelope.get('event') == name:
                return envelope
        time.sleep(0.02)
    raise AssertionError(f"no {name} event in {[e.get('event') for e in events]}")


def test_envelopes():
    """T-BRIDGE-1: the three envelopes, and a command read from either shape."""
    assert reply('a1', {'x': 1}) == {'id': 'a1', 'ok': True, 'data': {'x': 1}}
    assert reply('a1') == {'id': 'a1', 'ok': True, 'data': {}}
    assert error('a1', 'network', 'Offline.') == {
        'id': 'a1', 'ok': False, 'error': {'code': 'network', 'message': 'Offline.'}}
    assert event('log', {'line': 'x'}) == {'type': 'event', 'event': 'log', 'data': {'line': 'x'}}

    assert parse_command({'id': '1', 'command': 'boot', 'params': {'a': 2}}) == ('1', 'boot', {'a': 2})
    assert parse_command(json.dumps({'id': '1', 'command': 'boot'})) == ('1', 'boot', {})
    # A missing or malformed params block is an empty one, not a crash.
    assert parse_command({'id': '1', 'command': 'boot', 'params': None}) == ('1', 'boot', {})
    assert parse_command({}) == ('', '', {})


def test_unknown_commands_answer_rather_than_raise():
    """T-BRIDGE-2: nothing the UI can send gets out of `handle` as an exception."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge, _ = make_dispatcher(tmp)
        failure(bridge.handle({'id': 'x', 'command': 'does.not.exist'}), 'unknown')
        assert bridge.handle({'id': 'x', 'command': 'does.not.exist'})['id'] == 'x'
        for raw in ('not json at all', None, 42, '[1, 2]'):
            answer = bridge.handle(raw)
            assert answer['ok'] is False and answer['error']['code'] == 'unknown', (raw, answer)


def test_step_markers_track_the_real_log():
    """T-BRIDGE-3: the markers still follow the lines the flows really log.

    Ported from the Tk self-check: the step titles are the one thing inferred from the
    log, so they are checked against the real `logger.step` sequence -- nested lines
    included, since those are what a loose matcher trips over.
    """
    flows = {
        'create': (CREATE_STEPS, [
            'Setting up project structure...', 'Creating Modding Plugin...',
            'Downloading Convai dependencies...', 'Enabling required plugins...',
            'Saving project metadata...', 'Configuring project assets...',
            'Patching plugin source for engine compatibility...', 'Building project...',
        ]),
        'rebuild': (REBUILD_STEPS, ['Building project...']),
        'update': (UPDATE_STEPS, [
            'Loading project configuration...', 'Checking project engine version...',
            'Ensuring toolchain for UE 5.8...', 'Updating Convai dependencies...',
            'Removing 1 existing installation(s)...', 'Downloading latest dependencies...',
            'Configuring project assets...',
            'Patching plugin source for engine compatibility...', 'Building project...',
        ]),
        'migrate': (MIGRATE_STEPS, [
            'Getting target Unreal Engine version...', 'Updating selected project...',
            'Checking project engine version...', 'Ensuring toolchain for UE 5.6...',
            'Updating Convai dependencies...', 'Configuring project assets...',
            'Please select the target Unreal Engine 5.8 installation path...',
            'Creating copy of project for migration: MyScene_01_5.8',
            'Updating engine version to 5.8...', 'Setting project engine version to 5.8...',
            'Patching Target.cs files for target UE build compatibility...',
            'Patching plugin source for Unreal Engine 5.8 compatibility...',
            'Building migrated project with Unreal Engine 5.8...',
        ]),
    }

    for name, (steps, lines) in flows.items():
        marks, reached, current = step_marks(steps), [], -1
        for line in lines:
            hit = match_step(marks, current, line)
            if hit is not None:
                current = hit
                reached.append(hit)
        assert reached == list(range(len(steps))), (name, reached, step_titles(steps))

    # Only a logger.step line moves the list: a section banner repeats the whole
    # operation's name and would otherwise skip straight to a later step.
    marks = step_marks(UPDATE_STEPS)
    assert step_from_line(marks, -1, '\U0001f527 Loading project configuration...') == 0
    assert step_from_line(marks, -1, 'Loading project configuration...') is None
    assert step_from_line(marks, 0, '\U0001f527 Building project...') == 5
    assert step_from_line(marks, 5, '\U0001f527 Loading project configuration...') is None


def test_project_view_states():
    """T-BRIDGE-4: what the shelf says about a project, and what it never carries."""
    view = project_view('C:\\tools\\MyScene_01', {'asset_type': 'Scene', 'api_key': 'k'},
                        '5.6', '5.8', signed_in=True)
    assert view['name'] == 'MyScene_01' and view['ue'] == '5.6'
    assert view['migratable'] is True and view['stateTone'] == 'warn'
    assert view['state'].endswith('UE 5.8') and view['meta'] == 'UE 5.6'
    assert view['assetType'] == 'Scene' and view['connected'] is True
    assert 'k' not in json.dumps(view) and 'api_key' not in view

    same = project_view('C:\\tools\\Ready', {}, '5.8', '5.8', signed_in=False)
    assert same['migratable'] is False and same['state'] == 'Ready to update'
    assert same['stateTone'] == 'muted' and same['connected'] is False

    unknown = project_view('C:\\tools\\Legacy', {}, None, '5.8', signed_in=True)
    assert unknown['state'] == 'Engine version not detected' and unknown['stateTone'] == 'warn'
    assert unknown['migratable'] is False and unknown['ue'] == ''


def test_projects_and_preflight():
    """T-BRIDGE-5: the scan, and the migration naming taken from the real copy step."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)
        bridge, _ = make_dispatcher(tmp)

        projects = data(call(bridge, 'projects.list'))['projects']
        assert [p['name'] for p in projects] == ['MyScene_01'], projects
        assert projects[0]['ue'] == '5.6' and projects[0]['target'] == '5.8'
        assert 'project-key-abc' not in json.dumps(projects)

        before = data(call(bridge, 'migration.preflight', dir=project_dir))
        assert before['destinationName'] == 'MyScene_01_5.8', before
        assert before['destinationDir'] == os.path.join(tmp, 'MyScene_01_5.8')
        assert before['exists'] is False and before['needed'] is True
        assert (before['currentVersion'], before['targetVersion']) == ('5.6', '5.8'), before

        os.makedirs(before['destinationDir'])
        assert data(call(bridge, 'migration.preflight', dir=project_dir))['exists'] is True
        failure(call(bridge, 'project.migrate', dir=project_dir, enginePath=ENGINE,
                     targetEnginePath=ENGINE), 'destinationExists')

        failure(call(bridge, 'migration.preflight', dir=os.path.join(tmp, 'gone')), 'notFound')

        problem = data(call(bridge, 'project.validateName', name='MyScene_01'))['problem']
        assert problem and 'already exists' in problem, problem
        assert data(call(bridge, 'project.validateName', name='Fresh_01'))['problem'] is None


def test_run_streams_and_cleans_up():
    """T-BRIDGE-6: one run's log, steps and outcome -- and no handler left behind."""
    lines = ['Loading project configuration...', 'Checking project engine version...',
             'Updating Convai dependencies...', 'Configuring project assets...',
             'Patching plugin source for engine compatibility...', 'Building project...']

    def update_flow():
        logger.section('Updating Existing Modding Project')
        for line in lines:
            logger.step(line)
        return 'Convai plugin 3.2.0 replaced 3.1.0.'

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)
        bridge, events = make_dispatcher(tmp, flows={'update': update_flow})
        handlers = len(logger.logger.handlers)

        run_id = data(call(bridge, 'project.update', dir=project_dir, enginePath=ENGINE))['runId']
        assert run_id, 'a run answers with its id straight away'

        finished = wait_for(events, 'runFinished')['data']
        assert finished == {'runId': run_id, 'ok': True, 'subject': 'MyScene_01',
                            'folder': project_dir, 'notes': 'Convai plugin 3.2.0 replaced 3.1.0.',
                            'error': None,
                            'uproject': os.path.join(project_dir, 'MyScene_01.uproject'),
                            'rebuild': None}, finished

        assert len(logger.logger.handlers) == handlers, 'the queue handler must go with the run'
        logger.step('after the run')
        assert not [e for e in events if e['event'] == 'log' and 'after the run' in e['data']['line']]

        logged = [e['data']['line'] for e in events if e['event'] == 'log']
        assert all(any(line in text for text in logged) for line in lines), logged
        assert sum(lines[0] in text for text in logged) == 1, logged
        assert all(e['data']['runId'] == run_id for e in events if e['event'] in ('log', 'steps'))

        steps = [e for e in events if e['event'] == 'steps']
        assert steps[0]['data']['steps'][0]['state'] == 'active'
        final = steps[-1]['data']['steps']
        assert [s['state'] for s in final] == ['done'] * len(UPDATE_STEPS), final
        assert [s['title'] for s in final] == step_titles(UPDATE_STEPS)

        # The run is over, so the slot is free and the log is still there to save.
        assert bridge._run_id is None
        assert bridge._log_lines[run_id]


def test_migrate_run_names_the_copy():
    """T-BRIDGE-7: a migration primes both engines and reports the copy, not the source."""
    def migrate_flow():
        logger.step('Getting target Unreal Engine version...')
        return None

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)
        bridge, events = make_dispatcher(tmp, flows={'migrate': migrate_flow})
        target_engine = 'C:\\UE_5.8'

        run = data(call(bridge, 'project.migrate', dir=project_dir, enginePath=ENGINE,
                        targetEnginePath=target_engine))
        manager = bridge.input_manager
        assert manager.project_dir == project_dir
        assert (manager.unreal_engine_path, manager.target_unreal_engine_path) == (ENGINE, target_engine)

        finished = wait_for(events, 'runFinished')['data']
        assert finished['runId'] == run['runId'] and finished['ok'] is True
        assert finished['subject'] == 'MyScene_01_5.8', finished
        assert finished['folder'] == os.path.join(tmp, 'MyScene_01_5.8'), finished

        final = [e for e in events if e['event'] == 'steps'][-1]['data']['steps']
        assert [s['title'] for s in final] == step_titles(MIGRATE_STEPS)
        assert [s['state'] for s in final] == ['done'] * len(MIGRATE_STEPS), final


def test_failed_run_reports_its_reason():
    """T-BRIDGE-8: a flow that raises ends the run with the sentence it raised."""
    from core.exceptions import ProjectError

    def failing_flow():
        logger.step('Loading project configuration...')
        raise ProjectError('Unreal Engine 5.6 does not meet the modding project requirements')

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)
        bridge, events = make_dispatcher(tmp, flows={'update': failing_flow})
        handlers = len(logger.logger.handlers)

        call(bridge, 'project.update', dir=project_dir, enginePath=ENGINE)
        finished = wait_for(events, 'runFinished')['data']
        assert finished['ok'] is False
        assert 'does not meet' in finished['error'], finished
        assert len(logger.logger.handlers) == handlers
        # Nothing claims the run finished steps it never reached.
        for envelope in [e for e in events if e['event'] == 'steps']:
            states = [s['state'] for s in envelope['data']['steps']]
            assert states != ['done'] * len(UPDATE_STEPS), states


def test_a_finished_run_names_the_project_file():
    """T-BRIDGE-14: success carries the .uproject, so the UI can offer to open the project.

    Globbed, never composed from the folder: a migrated copy lives in `<name>_<version>/`
    but still holds `<name>.uproject`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp, name='MyScene_01')
        moved = os.path.join(tmp, 'MyScene_01_5.8')
        os.rename(project_dir, moved)

        bridge, events = make_dispatcher(tmp, flows={'update': lambda: None})
        call(bridge, 'project.update', dir=moved, enginePath=ENGINE)
        finished = wait_for(events, 'runFinished')['data']

        assert finished['ok'] is True, finished
        assert finished['uproject'] == os.path.join(moved, 'MyScene_01.uproject'), finished
        assert finished['rebuild'] is None, finished


def test_only_a_compile_failure_offers_a_rebuild():
    """T-BRIDGE-15: rerunning the compiler helps after a BuildError and nowhere else.

    Everything earlier leaves the project half-built, so compiling that again would report
    the same failure more slowly.
    """
    from core.exceptions import BuildError, ProjectError

    def raiser(exception):
        def flow():
            logger.step('Loading project configuration...')
            raise exception
        return flow

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)

        bridge, events = make_dispatcher(tmp, flows={'update': raiser(ProjectError('too early'))})
        call(bridge, 'project.update', dir=project_dir, enginePath=ENGINE)
        assert wait_for(events, 'runFinished')['data']['rebuild'] is None

        bridge, events = make_dispatcher(tmp, flows={'update': raiser(BuildError('C2039'))})
        call(bridge, 'project.update', dir=project_dir, enginePath=ENGINE)
        finished = wait_for(events, 'runFinished')['data']
        assert finished['rebuild'] == {'folder': project_dir, 'enginePath': ENGINE}, finished
        # The failure still reads as a failure; nothing is presented as built.
        assert finished['ok'] is False and finished['uproject'] is None, finished


def test_rebuild_compiles_and_nothing_else():
    """T-BRIDGE-16: project.rebuild runs the compiler against what the flow left behind.

    It must not re-enter a flow: a rebuild that downloaded again would delete the SDK
    plugins the failed run had already installed.
    """
    built = []
    original_build = UnrealEngineManager.__dict__['run_unreal_build']
    UnrealEngineManager.run_unreal_build = lambda self: built.append((self.ue_dir, self.project_name,
                                                                     self.project_dir))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            moved = os.path.join(tmp, 'MyScene_01_5.8')
            os.rename(make_project(tmp, name='MyScene_01'), moved)

            def must_not_run():
                raise AssertionError('a rebuild re-entered the update flow')

            bridge, events = make_dispatcher(tmp, flows={'update': must_not_run})
            data(call(bridge, 'project.rebuild', folder=moved, enginePath=ENGINE))
            finished = wait_for(events, 'runFinished')['data']

            assert finished['ok'] is True, finished
            # The project name comes off the .uproject, not off the folder it sits in.
            assert built == [(ENGINE, 'MyScene_01', moved)], built

            # A project that has been moved or deleted since the run, and a lost engine.
            failure(call(bridge, 'project.rebuild', folder=os.path.join(tmp, 'gone'),
                         enginePath=ENGINE), 'notFound')
            failure(call(bridge, 'project.rebuild', folder=moved, enginePath=''), 'invalidEngine')
            assert built == [(ENGINE, 'MyScene_01', moved)], 'a refused rebuild compiles nothing'
    finally:
        UnrealEngineManager.run_unreal_build = original_build

def test_one_run_at_a_time():
    """T-BRIDGE-9: a second run is refused, and the first one's answers are intact."""
    release = threading.Event()

    def slow_flow():
        logger.step('Setting up project structure...')
        release.wait(10)
        return None

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = make_project(tmp)
        bridge, events = make_dispatcher(tmp, flows={'create': slow_flow, 'update': slow_flow})

        started = data(call(bridge, 'project.create', name='Fresh_01', assetType='Avatar',
                            isMetahuman=True, enginePath=ENGINE))
        manager = bridge.input_manager
        assert (manager.project_name, manager.asset_type, manager.is_metahuman) == ('Fresh_01', 'Avatar', True)
        assert manager.convai_api_key == API_KEY and manager.unreal_engine_path == ENGINE

        failure(call(bridge, 'project.update', dir=project_dir, enginePath=ENGINE), 'busy')
        failure(call(bridge, 'project.create', name='Other_01', enginePath=ENGINE), 'busy')
        # The refused run must not have re-primed anything under the live one.
        assert manager.project_name == 'Fresh_01'

        release.set()
        finished = wait_for(events, 'runFinished')['data']
        assert finished['runId'] == started['runId'] and finished['ok'] is True
        assert finished['subject'] == 'Fresh_01' and finished['folder'] == os.path.join(tmp, 'Fresh_01')
        assert finished['notes'] is None

        # And the slot is free again.
        release.clear()
        release.set()
        assert data(call(bridge, 'project.update', dir=project_dir, enginePath=ENGINE))['runId']
        wait_for(events, 'runFinished')


def test_engine_choice_survives_a_reset():
    """T-BRIDGE-10: a chosen engine outlives `InputManager.reset()` between runs."""
    with tempfile.TemporaryDirectory() as tmp:
        chosen = []
        bridge, _ = make_dispatcher(tmp, choose_folder=lambda title: chosen.pop() if chosen else None)

        status = data(call(bridge, 'engine.status'))
        assert status['sameVersion'] is False, status
        assert status['current']['ready'] is False and status['current']['version'] == '5.6'
        assert 'Unreal Engine 5.6' in status['current']['reason']
        assert status['target']['path'] is None and status['target']['reason']

        # A cancelled picker leaves the engine exactly as it was.
        assert data(call(bridge, 'engine.choose', versionType='current'))['engine']['ready'] is False

        chosen.append('C:\\NotAnEngine')
        UnrealEngineManager.is_valid_current_engine_path = staticmethod(lambda path: False)
        failure(call(bridge, 'engine.choose', versionType='current'), 'invalidEngine')

        chosen.append(ENGINE)
        UnrealEngineManager.is_valid_current_engine_path = staticmethod(lambda path: True)
        engine = data(call(bridge, 'engine.choose', versionType='current'))['engine']
        assert engine == {'versionType': 'current', 'version': '5.6', 'path': ENGINE,
                          'ready': True, 'reason': None}, engine

        bridge.input_manager.reset()
        assert data(call(bridge, 'engine.status'))['current']['path'] == ENGINE

        # A remembered path is re-checked, never trusted: an engine that has gone reads
        # as not ready, with the reason in words.
        UnrealEngineManager.is_valid_current_engine_path = staticmethod(lambda path: False)
        current = data(call(bridge, 'engine.status'))['current']
        assert current['ready'] is False and current['path'] is None and current['reason']
        UnrealEngineManager.is_valid_current_engine_path = staticmethod(lambda path: True)


def test_account_replies_never_carry_the_key():
    """T-BRIDGE-11: the account shape is who is signed in, and nothing else."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge, events = make_dispatcher(tmp, signed_in=False)
        assert data(call(bridge, 'account.status'))['account'] == {
            'signedIn': False, 'name': None, 'email': ''}

        failure(call(bridge, 'project.create', name='Fresh_01', enginePath=ENGINE), 'notSignedIn')

        original_verify = dispatcher_module._verify_key
        try:
            dispatcher_module._verify_key = lambda key: None
            answers = [call(bridge, 'account.signInKey', key=API_KEY),
                       call(bridge, 'account.status'),
                       call(bridge, 'boot'),
                       call(bridge, 'account.signOut')]
        finally:
            dispatcher_module._verify_key = original_verify

        for answer in answers:
            assert API_KEY not in json.dumps(answer), answer
        assert API_KEY not in json.dumps(events), events

        signed_in = data(answers[1])['account']
        assert signed_in == {'signedIn': True, 'name': 'Convai account', 'email': ''}
        assert data(answers[3])['account']['signedIn'] is False
        assert [e['event'] for e in events if e['event'] == 'accountChanged'] == \
               ['accountChanged', 'accountChanged']

        boot = data(answers[2])
        assert boot['version'] == '3.0.6' and boot['requiredVersion'] == '9.9.9', boot
        assert boot['upToDate'] is None, 'an unreachable check is not an outdated build'
        assert data(call(bridge, 'updates.check')) == {'upToDate': None, 'latest': '9.9.9'}
        OfflineVersions.answer = True
        try:
            assert data(call(bridge, 'updates.check')) == {'upToDate': True, 'latest': '9.9.9'}
        finally:
            OfflineVersions.answer = None

        stages = [e['data'] for e in events if e['event'] == 'bootStage']
        assert stages == [{'stage': stage, 'state': state}
                          for stage in ('config', 'version', 'projects')
                          for state in ('active', 'done')], stages


def test_boot_reports_an_unreachable_config():
    """T-BRIDGE-13: a configuration fetch that failed is a network error, in plain words."""
    from core.exceptions import ConfigurationError

    def explode():
        raise ConfigurationError('Failed to load config after 5 attempts.')

    with tempfile.TemporaryDirectory() as tmp:
        bridge, events = make_dispatcher(tmp, signed_in=False)
        original_load = config.load
        try:
            config.load = explode
            message = failure(call(bridge, 'boot'), 'network')['message']
        finally:
            config.load = original_load
        assert 'connection' in message and 'attempts' not in message, message
        # Boot stopped where it failed rather than claiming the stage was done.
        assert [e['data'] for e in events if e['event'] == 'bootStage'] == [
            {'stage': 'config', 'state': 'active'}]


def test_dialogs_belong_to_the_host():
    """T-BRIDGE-14: without a host dialog the bridge says so rather than guessing."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge, _ = make_dispatcher(tmp)
        failure(call(bridge, 'engine.choose', versionType='current'), 'unknown')
        failure(call(bridge, 'log.save', runId='no-such-run'), 'notFound')
        failure(call(bridge, 'path.open', path=os.path.join(tmp, 'gone')), 'notFound')

        saved = os.path.join(tmp, 'run.log')
        bridge.save_file = lambda title, name: saved
        bridge._log_lines['r1'] = ['first line', 'second line']
        assert data(call(bridge, 'log.save', runId='r1')) == {'path': saved}
        with open(saved, encoding='utf-8') as handle:
            assert handle.read() == 'first line\nsecond line'

        # A cancelled save reports no path rather than an error.
        bridge.save_file = lambda title, name: None
        assert data(call(bridge, 'log.save', runId='r1')) == {}

        assert data(call(bridge, 'packaging.status')) == {'linuxEnabled': False, 'engineVersion': '5.6'}

        quit_calls = []
        bridge.on_quit = lambda: quit_calls.append(True)
        assert data(call(bridge, 'app.quit')) == {} and quit_calls == [True]


class OfflineVersions:
    """The version gate with no GitHub behind it: the check cannot be made."""

    answer = None

    @classmethod
    def check_version(cls, current_version):
        return cls.answer


original_version_manager = dispatcher_module._version_manager
original_detect = InputManager.detect_engine_path
original_valid = UnrealEngineManager.is_valid_current_engine_path
original_target_valid = UnrealEngineManager.is_valid_target_engine_path
# No registry, no filesystem: the engine is whatever the tests say it is.
dispatcher_module._version_manager = lambda: OfflineVersions
InputManager.detect_engine_path = staticmethod(lambda version_type='current': None)
UnrealEngineManager.is_valid_current_engine_path = staticmethod(lambda path: True)
UnrealEngineManager.is_valid_target_engine_path = staticmethod(lambda path: True)
try:
    test_envelopes()
    test_unknown_commands_answer_rather_than_raise()
    test_step_markers_track_the_real_log()
    test_project_view_states()
    test_projects_and_preflight()
    test_run_streams_and_cleans_up()
    test_migrate_run_names_the_copy()
    test_failed_run_reports_its_reason()
    test_a_finished_run_names_the_project_file()
    test_only_a_compile_failure_offers_a_rebuild()
    test_rebuild_compiles_and_nothing_else()
    test_one_run_at_a_time()
    test_engine_choice_survives_a_reset()
    test_account_replies_never_carry_the_key()
    test_boot_reports_an_unreachable_config()
    test_dialogs_belong_to_the_host()
finally:
    dispatcher_module._version_manager = original_version_manager
    InputManager.detect_engine_path = original_detect
    UnrealEngineManager.is_valid_current_engine_path = original_valid
    UnrealEngineManager.is_valid_target_engine_path = original_target_valid

config._remote_config = None
print('ok')

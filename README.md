An example on using JSON patch, SVS and AFrame to sync on VR/AR scenes.

# Run the application

Setup poetry environment:
```bash
poetry install
```

Run the application (needs local NFD):
```bash
poetry run python -m uvicorn main:app --port 8000
```

Then, browse http://127.0.0.1:8000/ to see the scene.

# Examples on operating objects

## Get the JSON representation of the box

```bash
curl http://127.0.0.1:8000/objects/root/theBox
```

The path `/root/theBox` can be replaced with any object.
This endpoint will automatically resolve sub-entities and return the full JSON representation.

## Change the box color to red

```bash
curl http://127.0.0.1:8000/patches/root/theBox -H 'Content-Type: application/json' \
  -d '{"op": "replace", "path": "/color", "value":"#EE0000"}'
```

## Create an octahedron

```bash
curl http://127.0.0.1:8000/patches/root/theOctahedron -H 'Content-Type: application/json' \
  -d '{"op":"new","value":{"@type":"a-octahedron","@children":{},"color":"#FF926B","radius":1,"position": "2 1.5 -4"}}'
curl http://127.0.0.1:8000/patches/root -H 'Content-Type: application/json' \
  -d '{"op": "add", "path": "/@children/theOctahedron", "value":-1}'
```

# Examples with SVS

- Run an instance on 8000: `poetry run python -m uvicorn main:app --port 8000`
- Run an instance on 8001: `poetry run python -m uvicorn main:app --port 8001`
- Manipulate objects on the 8000 instance. For example, add an octahedron.
- Check the 8001 scene at http://127.0.0.1:8001/, verify the modification is fetched.

# Discussion

- *Serverless*
  - Though this demo requires python-ndn and local NFD instance to run, all operations can be executed in a browser
    with ndn-ts. There is nothing must be executed on the backend.
    It is possible to migrate to ndn-ts and use textbed or WebRTC for connectivity
    Also, this demo requires manual reloading the page to see new changes,
    but no reload is required if we migrate to TS.
- *Decentralized*
  - This demo does not handle consensus problem properly. However, JSON patch can be extended to a conflict-free
    replicated data types (CRDT), which means eventual consensus is "automagically" reached irrelevant of
    the order of receiving the patches. No master server or leader election is needed.
- *Hierarchical namespace*
  - There are two kinds of data objects: scene objects (a-entities) and JSON patches (i.e. diffential updates of scene objects).
    Scene objects can be named in any hierarchical way according to application's need.
    Patches are named like `/<producer>/<sequence-number>`, according to the security's need.
  - Peers in the sync group will fetch all patches.
    Since scene objects can be recovered by JSON patches, they do not need to fetch scene objects directly.
- *Security*
  - Patches are signed by their producers.
  - Patches are immutable. Scene objects are updated via applying patches.

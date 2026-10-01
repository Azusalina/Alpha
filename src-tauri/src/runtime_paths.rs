//! Desktop-launch configuration only. Release never falls back to PATH Python.
use std::{ffi::OsString, io, path::{Path, PathBuf}};

pub(crate) fn release_paths(resources: &Path, python: Option<OsString>, root: Option<OsString>) -> io::Result<(OsString, PathBuf)> {
    // Release overrides are paired explicit absolute installations; never a
    // partially overridden interpreter mixed with the developer checkout.
    let (python, root) = match (python, root) {
        (None, None) => {
            if !resources.join("manifest.json").is_file()
                || !resources.join("ext-refs/jieba/jieba/__init__.py").is_file() {
                return Err(io::Error::new(io::ErrorKind::NotFound, "incomplete Alpha runtime resources"));
            }
            (resources.join("python/bin/python3"), resources.join("back-end-core"))
        }
        (Some(python), Some(root)) => (PathBuf::from(python), PathBuf::from(root)),
        _ => return Err(io::Error::new(io::ErrorKind::InvalidInput, "release requires both ALPHA_BRAIN_PYTHON and ALPHA_BRAIN_ROOT or neither")),
    };
    if !python.is_absolute() || !root.is_absolute() || !python.is_file() || !root.join("core/api.py").is_file() {
        return Err(io::Error::new(io::ErrorKind::NotFound, "missing absolute release Python/backend installation"));
    }
    Ok((python.into_os_string(), root))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn release_fails_closed() {
        let dir = tempfile::tempdir().unwrap();
        assert!(release_paths(dir.path(), None, None).is_err());
        assert!(release_paths(dir.path(), Some("python3".into()), None).is_err());
        assert!(release_paths(dir.path(), Some("python3".into()), Some(dir.path().into())).is_err());
    }
    #[test]
    fn complete_resource_layout() {
        let dir = tempfile::tempdir().unwrap();
        for file in ["manifest.json", "python/bin/python3", "back-end-core/core/api.py", "ext-refs/jieba/jieba/__init__.py"] {
            let path = dir.path().join(file);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, "fixture").unwrap();
        }
        let (python, root) = release_paths(dir.path(), None, None).unwrap();
        assert_eq!(PathBuf::from(python), dir.path().join("python/bin/python3"));
        assert_eq!(root, dir.path().join("back-end-core"));
    }
}

import React, { useState, useCallback, useMemo } from 'react';
import { Box, Menu, MenuItem, Typography } from '@mui/material';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import CodeIcon from '@mui/icons-material/Code';
import DescriptionIcon from '@mui/icons-material/Description';
import DataObjectIcon from '@mui/icons-material/DataObject';
import SearchIcon from '@mui/icons-material/Search';
import ArrowRightIcon from '@mui/icons-material/ArrowRight';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import { TooltippedButton } from '../mui-extras/tooltipped-button';
import { useActiveCellContext } from '../../contexts/active-cell-context';
import { useSelectionContext } from '../../contexts/selection-context';
import { useFileContext, IAvailableFile } from '../../contexts/file-context';
import { generateUniqueId } from '../../utils';

export enum CONTEXT_TYPE {
  SELECTED_CODE = 'selected-code',
  ACTIVE_BLOCK = 'active-block',
  CURRENT_FILE = 'current-file',
  FILE = 'FILE',
  COMPLETE_CONTEXT = 'complete-context'
}

export interface IAttachContext {
  id: string;
  type: CONTEXT_TYPE;
  label: string;
  filePath?: string;
  blockNumber?: number;
  startLine?: number;
  endLine?: number;
  content?: string;
}

export interface IAttachButtonProps {
  attachedContexts: IAttachContext[];
  setAttachedContexts: React.Dispatch<React.SetStateAction<IAttachContext[]>>;
}

export function AttachButton(props: IAttachButtonProps): JSX.Element {
  const [menuAnchorEl, setMenuAnchorEl] = useState<HTMLElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [fileMenuAnchorEl, setFileMenuAnchorEl] = useState<HTMLElement | null>(
    null
  );
  const [fileMenuOpen, setFileMenuOpen] = useState(false);
  const [availableFiles, setAvailableFiles] = useState<IAvailableFile[]>([]);

  const [textSelection] = useSelectionContext();
  const activeCell = useActiveCellContext();
  const { currentFile, getAvailableFiles, readFileContent } = useFileContext();

  const { hasTextSelection, selectedLinesCount } = useMemo(() => {
    return {
      hasTextSelection: !!textSelection?.text?.trim(),
      selectedLinesCount: textSelection?.numLines
    };
  }, [textSelection]);
  const { hasActiveCell } = useMemo(() => {
    return {
      hasActiveCell: !!activeCell.exists
    };
  }, [activeCell]);

  const { hasCurrentFile } = useMemo(() => {
    return {
      hasCurrentFile: !!currentFile
    };
  }, [currentFile]);

  const handleAddSelectedCode = useCallback(() => {
    if (!textSelection) {
      return;
    }

    const fileName = currentFile?.fileName || 'Unknown File';
    const startLine = textSelection?.start?.line + 1;
    const endLine = textSelection?.end?.line + 1;

    const lineLabel =
      startLine === endLine ? `${startLine}` : `${startLine}-${endLine}`;

    const context: IAttachContext = {
      id: generateUniqueId(),
      type: CONTEXT_TYPE.SELECTED_CODE,
      label: `${fileName}: ${lineLabel}`,
      startLine,
      endLine,
      content: textSelection.text
    };

    props.setAttachedContexts(prev => [...prev, context]);
    closeMenu();
  }, [textSelection, currentFile, props.setAttachedContexts]);

  const handleAddActiveBlock = useCallback(() => {
    if (!activeCell.exists) {
      return;
    }

    const cellContent = activeCell.manager.getContent(false);
    if (!cellContent) {
      return;
    }

    // Get file name and actual cell number
    const fileName = currentFile?.fileName || 'Notebook';
    const cellIndex = activeCell.manager.getCurrentCellIndex();
    const cellNumber = cellIndex >= 0 ? cellIndex + 1 : 1; // +1 for 1-based indexing
    const context: IAttachContext = {
      id: generateUniqueId(),
      type: CONTEXT_TYPE.ACTIVE_BLOCK,
      label: `${fileName}: Cell ${cellNumber}`,
      blockNumber: cellNumber,
      content: cellContent.source
    };

    props.setAttachedContexts(prev => [...prev, context]);
    closeMenu();
  }, [activeCell, currentFile, props.setAttachedContexts]);

  const handleAddCurrentFile = useCallback(async () => {
    if (!currentFile) {
      return;
    }

    const content = await readFileContent(currentFile.filePath);

    const context: IAttachContext = {
      id: generateUniqueId(),
      type: CONTEXT_TYPE.CURRENT_FILE,
      label: currentFile.fileName,
      filePath: currentFile.filePath,
      content: content
    };

    props.setAttachedContexts(prev => [...prev, context]);
    closeMenu();
  }, [currentFile, props.setAttachedContexts]);

  const handleAddCompleteContext = useCallback(() => {
    const context: IAttachContext = {
      id: generateUniqueId(),
      type: CONTEXT_TYPE.COMPLETE_CONTEXT,
      label: 'Complete Context',
      content: ''
    };

    props.setAttachedContexts(prev => [...prev, context]);
    closeMenu();
  }, [props.setAttachedContexts]);

  const openMenu = useCallback((el: HTMLElement | null) => {
    setMenuAnchorEl(el);
    setMenuOpen(true);
  }, []);

  const closeMenu = useCallback(() => {
    setMenuOpen(false);
  }, []);

  const openFileMenu = useCallback(
    async (el: HTMLElement | null) => {
      setFileMenuAnchorEl(el);
      setFileMenuOpen(true);

      // Load available files
      try {
        const files = await getAvailableFiles();
        setAvailableFiles(files.filter(f => f.type === 'file')); // Only show files for now
      } catch (error) {
        console.error('Failed to load files:', error);
        setAvailableFiles([]);
      }
    },
    [getAvailableFiles]
  );

  const closeFileMenu = useCallback(() => {
    setFileMenuOpen(false);
  }, []);

  const handleFileSelection = useCallback(
    async (file: IAvailableFile) => {
      try {
        const content = await readFileContent(file.path);
        const context: IAttachContext = {
          id: generateUniqueId(),
          type: CONTEXT_TYPE.FILE,
          label: file.name,
          filePath: file.path,
          content: content
        };

        props.setAttachedContexts(prev => [...prev, context]);
        closeFileMenu();
        closeMenu();
      } catch (error) {
        console.error('Failed to read file content:', error);
      }
    },
    [readFileContent, props.setAttachedContexts, closeFileMenu, closeMenu]
  );

  return (
    <Box>
      <TooltippedButton
        onClick={e => {
          openMenu(e.currentTarget);
        }}
        tooltip="Attach context to your message"
        buttonProps={{
          size: 'small',
          variant: 'outlined',
          onKeyDown: e => {
            if (e.key !== 'Enter' && e.key !== ' ') {
              return;
            }
            openMenu(e.currentTarget);
            e.stopPropagation();
          }
        }}
        sx={{
          minWidth: 'unset',
          p: 1,
          width: 32,
          height: 32,
          mr: 1
        }}
      >
        <AttachFileIcon fontSize="small" />
      </TooltippedButton>

      <Menu
        open={menuOpen}
        onClose={closeMenu}
        anchorEl={menuAnchorEl}
        anchorOrigin={{
          vertical: 'top',
          horizontal: 'left'
        }}
        transformOrigin={{
          vertical: 'bottom',
          horizontal: 'left'
        }}
        sx={{
          '& .MuiMenuItem-root': {
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            minWidth: '200px'
          },
          '& svg': {
            lineHeight: 0
          }
        }}
      >
        {hasTextSelection && (
          <MenuItem onClick={handleAddSelectedCode}>
            <CodeIcon fontSize="small" />
            <Box>
              <Typography display="block" fontSize="14px">
                Selected Code
              </Typography>
              <Typography
                display="block"
                sx={{ opacity: 0.618, fontSize: '12px' }}
              >
                {selectedLinesCount} lines selected
              </Typography>
            </Box>
          </MenuItem>
        )}

        {hasActiveCell && (
          <MenuItem onClick={handleAddActiveBlock}>
            <DataObjectIcon fontSize="small" />
            <Box>
              <Typography display="block" fontSize="14px">
                Active Block
              </Typography>
              <Typography
                display="block"
                sx={{ opacity: 0.618, fontSize: '12px' }}
              >
                Current active cell
              </Typography>
            </Box>
          </MenuItem>
        )}

        {hasCurrentFile && (
          <MenuItem onClick={handleAddCurrentFile}>
            <DescriptionIcon fontSize="small" />
            <Box>
              <Typography display="block" fontSize="14px">
                Add Current File
              </Typography>
              <Typography
                display="block"
                sx={{ opacity: 0.618, fontSize: '12px' }}
              >
                {currentFile?.fileName}
              </Typography>
            </Box>
          </MenuItem>
        )}

        <MenuItem onClick={handleAddCompleteContext}>
          <SearchIcon fontSize="small" />
          <Box>
            <Typography display="block" fontSize="14px">
              Complete Context
            </Typography>
            <Typography
              display="block"
              sx={{ opacity: 0.618, fontSize: '12px' }}
            >
              Project-wide vector search
            </Typography>
          </Box>
        </MenuItem>

        <MenuItem
          onClick={e => {
            e.stopPropagation();
            openFileMenu(e.currentTarget);
          }}
        >
          <FolderOpenIcon fontSize="small" />
          <Box sx={{ display: 'flex', alignItems: 'center', flex: 1 }}>
            <Box>
              <Typography display="block" fontSize="14px">
                Add File
              </Typography>
              <Typography
                display="block"
                sx={{ opacity: 0.618, fontSize: '12px' }}
              >
                Browse and select a file
              </Typography>
            </Box>
            <ArrowRightIcon fontSize="small" sx={{ marginLeft: 'auto' }} />
          </Box>
        </MenuItem>
      </Menu>

      {/* File selection submenu */}
      <Menu
        open={fileMenuOpen}
        onClose={closeFileMenu}
        anchorEl={fileMenuAnchorEl}
        anchorOrigin={{
          vertical: 'top',
          horizontal: 'right'
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'left'
        }}
        sx={{
          '& .MuiMenuItem-root': {
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            minWidth: '250px'
          },
          '& svg': {
            lineHeight: 0
          }
        }}
      >
        {availableFiles.length > 0 ? (
          availableFiles.map(file => (
            <MenuItem key={file.path} onClick={() => handleFileSelection(file)}>
              <DescriptionIcon fontSize="small" />
              <Box>
                <Typography display="block" fontSize="14px">
                  {file.name}
                </Typography>
                <Typography
                  display="block"
                  sx={{ opacity: 0.618, fontSize: '12px' }}
                >
                  {file.path}
                </Typography>
              </Box>
            </MenuItem>
          ))
        ) : (
          <MenuItem disabled>
            <Typography fontSize="14px" sx={{ opacity: 0.618 }}>
              No files available
            </Typography>
          </MenuItem>
        )}
      </Menu>
    </Box>
  );
}

/**
 * 3- CURRENT FILE
 * 4- FILES
 */

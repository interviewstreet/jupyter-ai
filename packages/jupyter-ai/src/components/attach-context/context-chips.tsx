import React from 'react';
import { Box, Chip } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import CodeIcon from '@mui/icons-material/Code';
import DescriptionIcon from '@mui/icons-material/Description';
import DataObjectIcon from '@mui/icons-material/DataObject';
import SearchIcon from '@mui/icons-material/Search';
import { CONTEXT_TYPE, IAttachContext } from './attach-button';

export interface IContextChipsProps {
  attachedContexts: IAttachContext[];
  setAttachedContexts: React.Dispatch<React.SetStateAction<IAttachContext[]>>;
}

function getIconForContextType(type: IAttachContext['type']): JSX.Element {
  switch (type) {
    case CONTEXT_TYPE.SELECTED_CODE:
      return <CodeIcon fontSize="small" />;
    case CONTEXT_TYPE.ACTIVE_BLOCK:
      return <DataObjectIcon fontSize="small" />;
    case CONTEXT_TYPE.CURRENT_FILE:
      return <DescriptionIcon fontSize="small" />;
    case CONTEXT_TYPE.COMPLETE_CONTEXT:
      return <SearchIcon fontSize="small" />;
    default:
      return <DescriptionIcon fontSize="small" />;
  }
}

export function ContextChips(props: IContextChipsProps): JSX.Element | null {
  if (props.attachedContexts.length === 0) {
    return null;
  }

  const handleRemoveContext = (contextId: string) => {
    props.setAttachedContexts(prev => prev.filter(ctx => ctx.id !== contextId));
  };

  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 1,
        p: 2,
        pt: 1,
        borderBottom: '1px solid #e0e0e0'
      }}
    >
      {props.attachedContexts.map(context => (
        <Chip
          key={context.id}
          icon={getIconForContextType(context.type)}
          label={context.label}
          size="small"
          variant="outlined"
          onDelete={() => handleRemoveContext(context.id)}
          deleteIcon={
            <CloseIcon
              fontSize="small"
              sx={{
                '&:hover': {
                  backgroundColor: 'rgba(0, 0, 0, 0.04)'
                }
              }}
            />
          }
          sx={{
            maxWidth: '300px',
            height: '24px',
            '& .MuiChip-label': {
              fontSize: '12px',
              fontWeight: 400,
              maxWidth: '200px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            },
            '& .MuiChip-icon': {
              fontSize: '14px',
              marginLeft: '4px'
            },
            '& .MuiChip-deleteIcon': {
              fontSize: '16px',
              marginRight: '2px'
            },
            backgroundColor: 'rgba(25, 118, 210, 0.04)',
            borderColor: 'rgba(25, 118, 210, 0.2)',
            color: 'rgba(25, 118, 210, 0.87)',
            '&:hover': {
              backgroundColor: 'rgba(25, 118, 210, 0.08)'
            }
          }}
        />
      ))}
    </Box>
  );
}

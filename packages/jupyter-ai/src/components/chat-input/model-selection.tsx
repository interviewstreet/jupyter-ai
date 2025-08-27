import React, { useCallback, useEffect, useState } from 'react';
import {
  Chip,
  ListItemText,
  Menu,
  MenuItem,
  Typography,
  Box,
  CircularProgress
} from '@mui/material';
import Check from '@mui/icons-material/Check';
import KeyboardArrowDown from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUp from '@mui/icons-material/KeyboardArrowUp';
import { AiService } from '../../handler';
import { useStackingAlert } from '../mui-extras/stacking-alert';

export type SupportedModel = {
  id: string;
  label: string;
  description: string;
};

export type SupportedModelsConfig = {
  provider: string;
  models: SupportedModel[];
};

const PROVIDER_ID = 'openai-chat-custom';
const DEFAULT_MODEL_OPTIONS: SupportedModel[] = [
  {
    id: 'gpt-4',
    label: 'GPT-4',
    description: 'Most capable model for complex, multi-step tasks'
  },
  {
    id: 'gpt-4o',
    label: 'GPT-4o',
    description: 'High-intelligence flagship model for complex, multi-step tasks'
  },
  {
    id: 'gpt-4o-mini',
    label: 'GPT-4o Mini',
    description: 'Affordable and intelligent small model for fast, lightweight tasks'
  },
  {
    id: 'gpt-4-turbo',
    label: 'GPT-4 Turbo',
    description: 'The latest GPT-4 Turbo model with vision capabilities'
  },
  {
    id: 'gpt-3.5-turbo',
    label: 'GPT-3.5 Turbo',
    description: 'Fast, inexpensive model for simple tasks'
  },
  {
    id: 'chatgpt-4o-latest',
    label: 'ChatGPT-4o Latest',
    description: 'Dynamic model continuously updated to the current version of ChatGPT'
  }
];

export function ModelSelection(): JSX.Element {
  // Alert for showing error messages to user
  const alert = useStackingAlert();

  const [selectedModel, setSelectedModel] = useState<SupportedModel>(
    DEFAULT_MODEL_OPTIONS[0]
  );
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);

  /**
   * Effect: load current completion model configuration on mount
   */
  useEffect(() => {
    async function loadCurrentCompletionModel() {
      try {
        const config = await AiService.getConfig();
        if (config.model_provider_id) {
          const mid = config.model_provider_id?.split(':')[1];
          const model =
            DEFAULT_MODEL_OPTIONS.find(m => m.id === mid) ??
            DEFAULT_MODEL_OPTIONS[0];
          setSelectedModel(model);
        }
      } catch (error) {
        console.error('Failed to load current completion model:', error);
      }
    }
    loadCurrentCompletionModel();
  }, []);

  /**
   * Handles model selection with optimistic UI updates and automatic rollback on failure
   * Updates both UI state and backend configuration
   */
  const handleModelSelection = useCallback(
    async (model: SupportedModel) => {
      setIsUpdating(true);
      const previousModel = selectedModel;
      setSelectedModel(model);
      setAnchor(null);

      try {
        const currentConfig = await AiService.getConfig();
        const lmGlobalId = `${PROVIDER_ID}:${model.id}`;
        const updateRequest: AiService.UpdateConfigRequest = {
          model_provider_id: lmGlobalId,
          last_read: currentConfig.last_read
        };

        await AiService.updateConfig(updateRequest);
        console.info(`✅ Updated model to: ${lmGlobalId}`, updateRequest);
      } catch (error) {
        console.error('❌ Failed to update completion model:', error);
        setSelectedModel(previousModel);
        const errorMessage =
          error instanceof Error
            ? error.message
            : 'Failed to update model configuration. Please try again.';
        alert.show('error', errorMessage);
      } finally {
        setIsUpdating(false);
      }
    },
    [selectedModel, alert]
  );

  return (
    <>
      <Chip
        clickable
        onClick={(event: React.MouseEvent<HTMLElement>) => {
          setAnchor(event.currentTarget as HTMLElement);
        }}
        variant="outlined"
        size="small"
        disabled={isUpdating}
        label={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" sx={{ lineHeight: 1 }}>
              {selectedModel?.label ?? 'Select model'}
            </Typography>
            {isUpdating ? (
              <CircularProgress size={14} />
            ) : anchor ? (
              <KeyboardArrowUp fontSize="small" />
            ) : (
              <KeyboardArrowDown fontSize="small" />
            )}
          </Box>
        }
        sx={{
          p: '0 2px 0'
        }}
      />

      <Menu
        open={!!anchor}
        onClose={() => setAnchor(null)}
        anchorEl={anchor}
        anchorOrigin={{ vertical: 'top', horizontal: 'left' }}
        transformOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        PaperProps={{
          sx: {
            border: '1px solid #e0e0e0',
            boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
            borderRadius: 4
          }
        }}
      >
        {DEFAULT_MODEL_OPTIONS.map(opt => {
          const isSelected = opt.id === selectedModel.id;
          return (
            <MenuItem
              key={opt.id}
              onClick={() => handleModelSelection(opt)}
              disabled={isUpdating}
            >
              <ListItemText>{opt.label}</ListItemText>
              {isSelected && <Check fontSize="small" />}
            </MenuItem>
          );
        })}
      </Menu>
      {alert.jsx}
    </>
  );
}

export default ModelSelection;

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MultiSelect, type SelectOption } from '../components/common/MultiSelect'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

const options: SelectOption[] = [
  { value: 'openalex', label: 'OpenAlex', description: 'Open academic graph' },
  { value: 'arxiv', label: 'arXiv', description: 'Preprints', needsKey: true },
]

describe('SouWen Google MultiSelect accessibility', () => {
  it('names the combobox and connects it to the listbox and filter input', async () => {
    const user = userEvent.setup()

    render(
      <MultiSelect
        ariaLabel="Data sources"
        options={options}
        selected={['arxiv']}
        onChange={vi.fn()}
        placeholder="Choose sources"
      />,
    )

    const combobox = screen.getByRole('combobox', { name: 'Data sources' })
    expect(combobox).toHaveAttribute('aria-expanded', 'false')
    expect(combobox).not.toHaveAttribute('aria-controls')

    await user.click(combobox)

    const listbox = screen.getByRole('listbox', { name: 'Data sources' })
    const filterInput = screen.getByRole('textbox', { name: 'multiselect.filter' })
    expect(combobox).toHaveAttribute('aria-expanded', 'true')
    expect(combobox).toHaveAttribute('aria-controls', listbox.id)
    expect(listbox).toHaveAttribute('aria-multiselectable', 'true')
    expect(filterInput).toHaveAttribute('aria-controls', listbox.id)
    expect(screen.getByRole('option', { name: /arXiv/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('falls back to placeholder text for its accessible name and exposes item actions', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <MultiSelect
        options={options}
        selected={['arxiv']}
        onChange={onChange}
        placeholder="Choose sources"
      />,
    )

    const combobox = screen.getByRole('combobox', { name: 'Choose sources' })
    await user.click(combobox)

    await user.type(screen.getByRole('textbox', { name: 'multiselect.filter' }), 'open')
    const listbox = screen.getByRole('listbox', { name: 'Choose sources' })
    expect(within(listbox).getByRole('option', { name: /OpenAlex/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /arXiv/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'common.cancel arXiv' }))

    expect(onChange).toHaveBeenCalledWith([])
  })
})
